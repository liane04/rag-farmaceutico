# CONTEXT2.md — Implementação da Fase 2: Pipeline de Ingestão

## Estado no início desta sessão

- Fase 1 (ambiente) ✅ — Python 3.13, venv, Docker, Qdrant em localhost:6333
- Fase 2 (ingestão) 🔄 em curso — sem código ainda
- Ficheiros existentes: `requirements.txt`, `.env`

---

## Ficheiros criados

### `src/config.py`
Configuração central do sistema. Lê variáveis do `.env` via `python-dotenv`.

| Variável | Valor padrão | Descrição |
|---|---|---|
| `GOOGLE_API_KEY` | `.env` | API key Gemini |
| `ANTHROPIC_API_KEY` | `.env` | API key Claude |
| `QDRANT_HOST` / `QDRANT_PORT` | `localhost:6333` | Ligação ao Qdrant |
| `QDRANT_COLLECTION` | `farmacos` | Nome da collection |
| `EMBEDDING_MODEL` | `models/gemini-embedding-2-preview` | Gemini Embedding 2 Preview |
| `GENERATIVE_MODEL` | `claude-3-5-sonnet-20241022` | Claude 3.5 Sonnet |
| `EMBEDDING_DIMENSION` | `3072` | Dimensão do vetor |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `4000` / `800` | Caracteres (~1000/~200 tokens) |
| `RETRIEVAL_TOP_K` / `RERANK_TOP_N` | `10` / `3` | Recuperação e reranking |
| `FAITHFULNESS_THRESHOLD` | `0.85` | Guardrail de output |
| `RELEVANCE_THRESHOLD` | `0.80` | Threshold CRAG |

---

### `src/ingestion/loader.py`
Extração de conteúdo de PDFs farmacêuticos.

**Dependências:** `PyMuPDF` (fitz), `pdfplumber`

**Funções principais:**

- `carregar_pdf(caminho, tipo_documento)` → `DocumentoExtraido`
  - Texto corrido por página via PyMuPDF
  - Tabelas por página via pdfplumber (serialização `col1 | col2 | ...`)
  - Limpeza: remove números de página isolados, linhas < 3 chars, colapsa linhas em branco
- `carregar_pasta(pasta, mapeamento_tipos)` → `list[DocumentoExtraido]`
  - Carrega todos os `.pdf` de um diretório
  - Aceita mapeamento `{nome_ficheiro: tipo_documento}`

**Dataclass `DocumentoExtraido`:**
```python
ficheiro: str
paginas: list[dict]   # [{numero, texto, tabelas}]
tipo_documento: str   # "bula", "monografia", "guideline", ...
total_paginas: int
```

---

### `src/ingestion/chunker.py`
Divisão de texto em chunks com metadados de rastreabilidade.

**Dependências:** `langchain-text-splitters`

**Estratégia:**
1. Por cada página: combina texto corrido + tabelas num único bloco
2. Aplica `RecursiveCharacterTextSplitter` com separadores `["\n\n", "\n", ". ", ...]`
3. Associa metadados a cada chunk

**Funções principais:**

- `chunkar_documento(documento, chunk_size, chunk_overlap)` → `list[Chunk]`
- `chunkar_documentos(documentos, ...)` → `list[Chunk]`

**Dataclass `Chunk`:**
```python
texto: str
metadados: {
    ficheiro, tipo_documento, pagina,
    chunk_index, tem_tabela
}
```

---

### `src/ingestion/embedder.py`
Geração de embeddings com Gemini Embedding 2.

**Dependências:** `langchain-google-genai`

**Detalhe de implementação:**
- `task_type="RETRIEVAL_DOCUMENT"` para indexação
- `task_type="RETRIEVAL_QUERY"` para queries em tempo real
- Processamento em lotes de 50 com pausa de 1s entre lotes (rate limiting)

**Funções principais:**

- `criar_embedder(task_type)` → `GoogleGenerativeAIEmbeddings`
- `gerar_embeddings(chunks, embedder)` → `list[tuple[Chunk, list[float]]]`
- `gerar_embedding_query(query, embedder)` → `list[float]` ← usado no pipeline de consulta (Fase 3)

---

### `src/ingestion/indexer.py`
Indexação no Qdrant com suporte a recuperação híbrida.

**Dependências:** `qdrant-client`

**Configuração da collection:**
- Vetor denso `"dense"`: dimensão 3072, distância Cosine
- Vetor esparso `"sparse"`: BM25-like para keyword search
- Payload: `texto` + todos os metadados do chunk

**Funções principais:**

- `criar_cliente()` → `QdrantClient`
- `garantir_collection(cliente, nome)` — cria se não existir, reutiliza se existir
- `indexar_chunks(pares, cliente, nome_collection, tamanho_lote)` → `int` (total indexado)
- `contar_pontos(cliente, nome_collection)` → `int`

**Nota sobre BM25:** A implementação atual usa `hashlib.md5` (determinístico) para mapear tokens a índices esparsos. Para produção, substituir por um tokenizador BM25 dedicado (ex: `rank_bm25`).

---

### `src/ingestion/pipeline.py`
Orquestração completa das 4 etapas.

**Uso via CLI:**
```bash
# Ingerir uma pasta inteira
python -m src.ingestion.pipeline --pasta data/documents

# Ingerir um ficheiro específico
python -m src.ingestion.pipeline --ficheiro data/documents/bula_x.pdf --tipo bula
```

**Fluxo:**
```
PDFs → loader → DocumentoExtraido
             → chunker → list[Chunk]
                       → embedder → list[(Chunk, vetor)]
                                  → indexer → Qdrant
```

---

### `requirements.txt` (atualizado)
Adicionado `langchain-text-splitters` (necessário para `chunker.py`).

```
langchain
langchain-text-splitters    ← adicionado
langchain-google-genai<2.0  ← versão fixada (ver nota abaixo)
langchain-anthropic
langchain-qdrant
pymupdf
pdfplumber
qdrant-client
fastapi
uvicorn
python-dotenv
```

> **Nota:** `langchain-google-genai>=2.0` usa o SDK `google-genai` que acede ao endpoint `v1beta`, onde `models/text-embedding-004` não está disponível. A versão `<2.0` usa `google-generativeai` e o endpoint correto.

---

### `data/documents/`
Pasta criada para receber os PDFs a ingerir (bulas, monografias, guidelines INFARMED).

---

## Como testar a Fase 2

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Preencher as API keys no .env
#    GOOGLE_API_KEY=...
#    ANTHROPIC_API_KEY=...

# 3. Garantir que o Qdrant está a correr
docker ps   # verificar container qdrant

# 4. Colocar um PDF em data/documents/

# 5. Correr o pipeline
python -m src.ingestion.pipeline --pasta data/documents
```

Output esperado:
```
=== PIPELINE DE INGESTÃO ===
-- Etapa 1: Carregamento de PDFs --
   1 documento(s) carregado(s)
-- Etapa 2: Chunking --
   N chunk(s) gerado(s)
-- Etapa 3: Geração de embeddings (Gemini) --
   N embedding(s) gerado(s)
-- Etapa 4: Indexação no Qdrant --
   N ponto(s) indexado(s)
=== Pipeline concluído em Xs ===
```

---

## Revisão e correções aplicadas

Após a criação inicial dos ficheiros, foi feita uma revisão completa que identificou e corrigiu:

| Ficheiro | Problema | Correção |
|---|---|---|
| `config.py` | `CHUNK_SIZE=1000` era tratado como caracteres pelo splitter, não tokens | Alterado para `4000` chars (~1000 tokens), overlap `800` (~200 tokens) |
| `config.py` | `GENERATIVE_MODEL` apontava para modelo errado | Corrigido para `claude-3-5-sonnet-20241022` |
| `indexer.py` | `hash()` do Python é randomizado entre execuções (PYTHONHASHSEED) — vetores esparsos ficavam inconsistentes | Substituído por `hashlib.md5` (determinístico) |
| `indexer.py` | Retornava `dict` em vez do tipo esperado pelo Qdrant | Retorna agora `SparseVector` do qdrant-client |
| `loader.py` | `field` e `Optional` importados sem uso | Removidos |
| `indexer.py` | `VectorsConfig` importado sem uso | Removido |
| `pipeline.py` | `sys` importado sem uso; import lazy dentro de função | Limpos e movidos para o topo |
| `config.py` | `models/text-embedding-004` não disponível no endpoint `v1beta` usado pelo SDK | Alterado para `models/gemini-embedding-2-preview` (3072 dims); `EMBEDDING_DIMENSION` atualizado |
| `requirements.txt` | `langchain-google-genai>=2.0` usa SDK `google-genai` incompatível com o modelo de embedding | Fixado para `<2.0` |
| `indexer.py` | `_texto_para_sparse` produzia índices duplicados em caso de colisão de hash | Corrigido com dicionário de agregação (soma de pesos por índice) |

---

## Fase seguinte: Fase 3 — Pipeline de Consulta

Ficheiros a criar:
- `src/ingestion/embedder.py` → `gerar_embedding_query` já implementada
- `src/retrieval/retriever.py` — recuperação híbrida Qdrant (dense + sparse, top 10)
- `src/retrieval/reranker.py` — LLM-as-Judge com Claude (top 10 → top 3)
- `src/retrieval/crag.py` — avaliação de relevância + reformulação de query
- `src/generation/generator.py` — geração de resposta com citação de fontes
- `src/generation/prompt.py` — templates de prompt
- `src/guardrails/input_guard.py` — validação de domínio + anti-prompt injection
- `src/guardrails/output_guard.py` — fidelidade + disclaimer obrigatório
