# CONTEXT3.md — Correcoes da Fase 2 + Implementacao da Fase 3: Pipeline de Consulta

## Estado no inicio desta sessao

- Fase 1 (ambiente) ✅
- Fase 2 (ingestao) ✅ — codigo funcional, mas com problemas de duplicados e tipos
- Fase 3 (consulta) ❌ — pastas `query/` e `guardrails/` vazias
- Fase 4 (API) ❌

---

## Correcoes da Fase 2

### Problema 1: Tipos de documento "desconhecido"

Os PDFs eram ingeridos sem tipo porque o `TIPOS_PADRAO` no pipeline exigia hardcodar nomes de ficheiros — nao escalavel.

**Solucao:** Convencao de subpastas. O loader infere o tipo a partir da pasta onde o PDF esta:

```
data/documents/
├── bulas/            -> tipo "bula"
├── monografias/      -> tipo "monografia"
├── guidelines/       -> tipo "guideline"
└── normas/           -> tipo "norma"
```

**Ficheiros alterados:**
- `src/ingestion/loader.py` — `carregar_pasta()` agora usa `rglob("*.pdf")` para percorrer subpastas e infere o tipo via dicionario `tipos_por_pasta`. Mapeamento explicito continua a funcionar como override.

**Subpastas reconhecidas:**
| Subpasta | Tipo inferido |
|---|---|
| `bulas/` | `bula` |
| `monografias/` | `monografia` |
| `guidelines/` | `guideline` |
| `normas/` | `norma` |

PDFs na raiz ou em subpastas nao reconhecidas ficam como `"desconhecido"`.

---

### Problema 2: Duplicados no Qdrant

Cada execucao do pipeline gerava UUIDs aleatorios (`uuid.uuid4()`), criando pontos duplicados no Qdrant.

**Solucao:** IDs deterministicos com `uuid.uuid5()` baseados em `ficheiro:pagina:chunk_index`. O `upsert` do Qdrant sobrepoe pontos com o mesmo ID em vez de duplicar.

**Ficheiro alterado:**
- `src/ingestion/indexer.py` — substituido `uuid.uuid4()` por:
```python
chave = f"{chunk.metadados['ficheiro']}:{chunk.metadados['pagina']}:{chunk.metadados['chunk_index']}"
ponto_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave))
```

**Teste de idempotencia:** Pipeline corrido 2x seguidas → total manteve-se em 31 pontos.

---

### Problema 3: Encoding Windows

O caractere `→` nos prints causava `UnicodeEncodeError` no Windows (cp1252).

**Ficheiro alterado:**
- `src/ingestion/loader.py` — substituido `→` por `--` nos prints do loader.

---

### Reorganizacao dos documentos

Os PDFs foram movidos para as subpastas corretas:
- `brufen.pdf` → `data/documents/monografias/`
- `brufen_folheto.pdf` → `data/documents/bulas/`

Collection Qdrant apagada e re-ingerida com tipos corretos:
```
brufen_folheto.pdf → tipo: bula
brufen.pdf → tipo: monografia
Total: 31 pontos (sem duplicados)
```

---

## Implementacao da Fase 3 — Pipeline de Consulta

### Ficheiros criados

#### `src/query/__init__.py`
Ficheiro vazio para registo do modulo.

#### `src/guardrails/__init__.py`
Ficheiro vazio para registo do modulo.

---

#### `src/query/retriever.py`
Recuperacao hibrida no Qdrant (densa + esparsa).

**Dependencias:** `qdrant-client`, `src.ingestion.embedder`, `src.ingestion.indexer`

**Mecanismo:**
1. Gera embedding denso da query (Gemini, `RETRIEVAL_QUERY`)
2. Gera vetor esparso da query (BM25-like, reutiliza `_texto_para_sparse` do indexer)
3. Envia ambos ao Qdrant com fusao RRF (Reciprocal Rank Fusion)
4. Opcionalmente filtra por `tipo_documento`

**Funcao principal:**
- `recuperar(query, top_k, tipo_documento, cliente)` → `list[ChunkRecuperado]`

**Dataclass `ChunkRecuperado`:**
```python
texto: str
metadados: dict       # ficheiro, tipo_documento, pagina, chunk_index, tem_tabela
score: float          # score combinado (RRF)
ponto_id: str         # ID do ponto no Qdrant
```

**Pesquisa hibrida:** Usa `Prefetch` do Qdrant para fazer duas pesquisas em paralelo (densa e esparsa) e fundir os resultados via `FusionQuery(fusion=Fusion.RRF)`.

---

#### `src/query/reranker.py`
Reranking de chunks com LLM-as-Judge (Claude).

**Dependencias:** `anthropic`

**Mecanismo:**
1. Formata os top_k chunks como excertos numerados
2. Envia ao Claude com prompt de avaliacao (escala 0-10)
3. Parseia resposta JSON com scores e justificacoes
4. Seleciona os top_n com maior score

**Funcao principal:**
- `rerankar(query, chunks, top_n)` → `list[ChunkRecuperado]`

**Fallback:** Se o parsing do JSON falhar, mantem a ordem original do retriever.

---

#### `src/query/prompt.py`
Templates de prompt centralizados.

**Prompts definidos:**
| Nome | Uso |
|---|---|
| `SYSTEM_PROMPT` | System prompt farmaceutico com regras obrigatorias (citacoes, disclaimer, sem alucinacoes) |
| `PROMPT_GERACAO` | Template para geracao de resposta com contexto e query |
| `PROMPT_CRAG_AVALIACAO` | Avaliacao de relevancia dos chunks (JSON: relevante, confianca, razao) |
| `PROMPT_CRAG_REFORMULACAO` | Reformulacao da query com termos tecnicos farmaceuticos |

---

#### `src/query/crag.py`
Corrective RAG — avaliacao de relevancia e reformulacao de query (RF06, RF07).

**Dependencias:** `anthropic`

**Pipeline CRAG:**
1. Avalia se os chunks rerankados sao relevantes (`confianca >= RELEVANCE_THRESHOLD`)
2. Se insuficientes, reformula a query com termos farmaceuticos
3. Re-recupera e re-avalia com a query reformulada
4. Se ainda insuficiente, sinaliza `contexto_suficiente=False`

**Funcoes principais:**
- `avaliar_relevancia(query, chunks)` → `dict` (relevante, confianca, razao)
- `reformular_query(query)` → `str`
- `crag_pipeline(query, chunks, recuperar_fn)` → `(chunks, contexto_suficiente, query_usada)`

**Constantes:** `MAX_TENTATIVAS = 2` (query original + 1 reformulacao)

---

#### `src/query/generator.py`
Geracao de resposta fundamentada com citacao de fontes (RF08, RF13).

**Dependencias:** `anthropic`

**Mecanismo:**
1. Formata chunks como contexto numerado com fontes
2. Envia ao Claude com `SYSTEM_PROMPT` + `PROMPT_GERACAO`
3. Se `contexto_suficiente=False` (CRAG), adiciona nota de qualidade
4. Extrai lista unica de fontes (ficheiro, pagina, tipo)

**Funcao principal:**
- `gerar_resposta(query, chunks, contexto_suficiente, query_usada)` → `RespostaRAG`

**Dataclass `RespostaRAG`:**
```python
resposta: str
query_usada: str          # query original ou reformulada (CRAG)
contexto_suficiente: bool
chunks_usados: list[ChunkRecuperado]
fontes: list[dict]         # [{ficheiro, pagina, tipo_documento}]
```

---

#### `src/guardrails/input_guard.py`
Guardrail de input — validacao de dominio e detecao de prompt injection (RF05).

**3 verificacoes por ordem (da mais barata a mais cara):**
1. **Comprimento** — min 5, max 2000 caracteres (instantaneo)
2. **Prompt injection** — regex contra padroes conhecidos em PT e EN (instantaneo)
3. **Dominio farmaceutico** — LLM classifica como SIM/NAO (chamada ao Claude)

**Padroes de injection detetados:** `ignora instrucoes`, `esquece tudo`, `finge que`, `system prompt`, `jailbreak`, `DAN mode`, `ignore previous`, etc.

**Funcao principal:**
- `validar_input(query)` → `(valido, mensagem_erro)`

---

#### `src/guardrails/output_guard.py`
Guardrail de output — fidelidade e disclaimer obrigatorio (RF13, RF14).

**2 verificacoes:**
1. **Disclaimer** — verifica presenca de keywords obrigatorias (`substitui`, `julgamento`, `profissional`, `documentacao original`, `fontes citadas`). Se ausente, adiciona automaticamente.
2. **Fidelidade** — LLM compara resposta com excertos originais (score 0-1). Se abaixo de `FAITHFULNESS_THRESHOLD` (0.85), adiciona nota de qualidade.

**Funcao principal:**
- `validar_output(resposta, chunks)` → `(valido, resposta_final, detalhes_fidelidade)`

---

#### `src/query/pipeline.py`
Orquestracao completa do pipeline de consulta.

**Uso via CLI:**
```bash
python -m src.query.pipeline "Quais sao os efeitos secundarios do ibuprofeno?"
python -m src.query.pipeline "O que faz o Brufen?" --tipo bula
```

**Pipeline (6 etapas):**
```
Query → input_guard → retriever (top 10) → reranker (top 3)
      → CRAG (avaliar/reformular) → generator → output_guard → Resposta
```

**Funcao principal:**
- `consultar(query, tipo_documento, verbose)` → `RespostaRAG`

---

## Testes realizados

### Teste 1: "Quais sao os efeitos secundarios do ibuprofeno?"
- Input valido ✅
- 10 chunks recuperados → 3 apos reranking
- CRAG: relevante=True, confianca=1.00
- Fidelidade: 1.00
- Resposta detalhada com efeitos organizados por sistema de orgaos
- Fontes: brufen.pdf p.10 (monografia) + brufen_folheto.pdf p.10-11 (bula)
- Tempo: 49.8s

### Teste 2: "O que faz o brufen?"
- Input valido ✅
- 10 chunks recuperados → 3 apos reranking
- CRAG: relevante=True, confianca=0.95
- Fidelidade: 1.00
- Disclaimer detetado corretamente (sem duplicar) ✅
- Fontes: brufen_folheto.pdf p.1 (bula) + brufen.pdf p.1-2 (monografia)
- Tempo: 36.5s

### Problema detetado e corrigido: Disclaimer duplicado
No Teste 1, o Claude incluiu disclaimer com acentos (`Não substitui`) mas o output_guard procurava versao sem acentos (`nao substitui`). Resultado: disclaimer adicionado em duplicado.

**Correcao:** Keywords do disclaimer simplificadas para palavras parciais que funcionam com e sem acentos (`substitui`, `julgamento`, `profissional`).

---

## Modelo generativo

Modelo atualizado de `claude-3-5-sonnet-20241022` (404 not found) para `claude-sonnet-4-5` no `config.py`.

---

## Nota sobre performance

Os testes demoram ~35-50s porque o pipeline faz 5 chamadas ao Claude:
1. Input guard (verificacao de dominio)
2. Reranker (LLM-as-Judge)
3. CRAG (avaliacao de relevancia)
4. Generator (geracao de resposta)
5. Output guard (verificacao de fidelidade)

O RNF01 especifica <=10s. Otimizacoes possiveis para producao:
- Paralelizar input guard com recuperacao (independentes)
- Cache de queries frequentes
- Usar modelo mais leve para guardrails (ex: Haiku)

---

## Estado da Implementacao (atualizado)

| Fase | Estado |
|---|---|
| Fase 1 — Ambiente e infraestrutura | ✅ Completo |
| Fase 2 — Pipeline de ingestao | ✅ Completo (corrigido: tipos, duplicados, encoding) |
| Fase 3 — Pipeline de consulta | ✅ Completo (retriever, reranker, CRAG, generator, guardrails) |
| Fase 4 — API e interface | ❌ Por fazer |

---

## Estrutura de ficheiros (atualizada)

```
src/
├── __init__.py
├── config.py
├── ingestion/
│   ├── __init__.py
│   ├── loader.py        # Extracao de PDFs (PyMuPDF + pdfplumber)
│   ├── chunker.py       # Chunking com metadados
│   ├── embedder.py      # Embeddings Gemini
│   ├── indexer.py       # Indexacao Qdrant (IDs deterministicos)
│   └── pipeline.py      # Orquestracao ingestao
├── query/
│   ├── __init__.py
│   ├── retriever.py     # Recuperacao hibrida (densa + esparsa + RRF)
│   ├── reranker.py      # LLM-as-Judge (Claude)
│   ├── crag.py          # Corrective RAG (avaliacao + reformulacao)
│   ├── generator.py     # Geracao de resposta com citacoes
│   ├── prompt.py        # Templates de prompt centralizados
│   └── pipeline.py      # Orquestracao consulta
├── guardrails/
│   ├── __init__.py
│   ├── input_guard.py   # Validacao dominio + anti-injection
│   └── output_guard.py  # Fidelidade + disclaimer
└── api/                 # (Fase 4 — por fazer)

data/documents/
├── bulas/
│   └── brufen_folheto.pdf
├── monografias/
│   └── brufen.pdf
├── guidelines/          # (vazia, pronta)
└── normas/              # (vazia, pronta)
```

---

## Fase seguinte: Fase 4 — API e Interface

Ficheiros a criar:
- `src/api/__init__.py`
- `src/api/main.py` — FastAPI app com endpoints REST
- `src/api/models.py` — Schemas Pydantic (request/response)
- `src/api/audit.py` — Registo de auditoria (RF09, Art. 12 EU AI Act)
- `docker-compose.yml` — Qdrant + app
- Interface web (a definir: Streamlit, HTML simples, ou apenas Swagger UI)
