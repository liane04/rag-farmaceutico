# CONTEXT4.md — Testes + Fase 4: API REST (FastAPI)

## Estado no inicio desta sessao

- Fase 1 (ambiente) ✅
- Fase 2 (ingestao) ✅
- Fase 3 (consulta) ✅
- Fase 4 (API) ❌ — pasta `src/api/` vazia
- Testes ❌ — pasta `tests/` nao existia

---

## Testes

### Configuracao

- Framework: **pytest** + **pytest-html** (relatorios)
- Ficheiro de configuracao: `pytest.ini` com marker `integration` para separar testes unitarios de integracao
- Pasta de relatorios: `tests/reports/` (adicionada ao `.gitignore`)

### Ficheiros criados

| Ficheiro | Tipo | Testes | O que testa |
|---|---|---|---|
| `tests/test_loader.py` | Unitario | 11 | Extracao de PDFs, inferencia de tipo por subpasta, erros |
| `tests/test_chunker.py` | Unitario | 11 | Chunking, metadados, tamanho, overlap, indice sequencial |
| `tests/test_indexer.py` | Unitario | 9 | Vetores esparsos (BM25), IDs deterministicos (uuid5) |
| `tests/test_input_guard.py` | Unitario | 16 | Prompt injection (PT+EN), comprimento, queries seguras |
| `tests/test_output_guard.py` | Unitario | 6 | Detecao de disclaimer (com/sem acentos, parcial, vazio) |
| `tests/test_retriever.py` | Integracao | 7 | Recuperacao hibrida, top_k, filtragem por tipo, metadados |
| `tests/test_pipeline.py` | Integracao | 6 | End-to-end: query valida, fontes, disclaimer, injection, query curta |

**Total: 66 testes — todos a passar.**

### Problemas encontrados e corrigidos

| Problema | Correcao |
|---|---|
| Regex `DAN\s+mode` nao detetava "DAN mode" porque `query.lower()` transformava em "dan" | Alterado para `dan\s+mode` em `input_guard.py` |
| numpy 2.4.4 bloqueado pela politica de seguranca do Windows (DLL) | Downgrade para `numpy<2.0` (versao 1.26.4) |
| `load_dotenv()` nao carregava `ANTHROPIC_API_KEY` (variavel de ambiente vazia sobrepunha o `.env`) | Adicionado `override=True` em `config.py` |

### Como correr os testes

```bash
# Todos os testes
python -m pytest tests/ -v

# Apenas unitarios (sem APIs)
python -m pytest tests/test_loader.py tests/test_chunker.py tests/test_indexer.py tests/test_input_guard.py tests/test_output_guard.py -v

# Apenas integracao (precisa de Qdrant + API keys)
python -m pytest tests/test_retriever.py tests/test_pipeline.py -v

# Gerar relatorio HTML
python -m pytest tests/ -v --html=tests/reports/report.html --self-contained-html
```

---

## Fase 4 — API REST (FastAPI)

### Ficheiros criados

#### `src/api/__init__.py`
Ficheiro vazio para registo do modulo.

---

#### `src/api/models.py`
Schemas Pydantic para validacao automatica e documentacao Swagger.

**Schemas de request:**
| Schema | Campos |
|---|---|
| `ConsultaRequest` | `query` (str, 5-2000 chars), `tipo_documento` (str opcional) |

**Schemas de response:**
| Schema | Campos |
|---|---|
| `ConsultaResponse` | `resposta`, `query_usada`, `contexto_suficiente`, `fontes`, `num_chunks_usados` |
| `FonteResponse` | `ficheiro`, `pagina`, `tipo_documento` |
| `DocumentoResponse` | `ficheiro`, `tipo_documento`, `total_chunks`, `paginas` |
| `DocumentosListResponse` | `documentos`, `total_documentos`, `total_chunks` |
| `IngestaoResponse` | `documentos_carregados`, `chunks_gerados`, `pontos_indexados`, `total_na_collection`, `duracao_segundos` |
| `HealthResponse` | `status`, `qdrant`, `collection`, `total_pontos` |
| `ErroResponse` | `erro`, `detalhe` |

---

#### `src/api/audit.py`
Registo de auditoria imutavel (append-only) para conformidade com RF09 e EU AI Act Art. 12.

**Mecanismo:**
- Cada consulta gera um registo em formato JSONL (uma linha JSON por registo)
- Um ficheiro por dia: `data/audit/audit_YYYY-MM-DD.jsonl`
- Append-only (nunca edita registos anteriores)

**Campos registados:**
- `id` — identificador unico (timestamp com microsegundos)
- `timestamp` — data/hora UTC em formato ISO 8601
- `query_original` — pergunta do utilizador
- `query_usada` — query apos possivel reformulacao CRAG
- `contexto_suficiente` — flag do CRAG
- `resposta` — texto completo da resposta gerada
- `fontes` — fontes documentais citadas
- `num_chunks` — numero de chunks usados
- `duracao_segundos` — tempo total do pipeline
- `fidelidade` — score do output guard
- `ip_cliente` — IP de origem do pedido

**Funcao principal:**
- `registar_consulta(...)` → `str` (audit_id)

---

#### `src/api/main.py`
Aplicacao FastAPI com 5 endpoints REST.

**Configuracao:**
- CORS habilitado (todas as origens — ajustar em producao)
- Swagger UI automatico em `/docs`
- ReDoc em `/redoc`

**Endpoints:**

| Metodo | Endpoint | Descricao |
|---|---|---|
| POST | `/consulta` | Envia uma pergunta e recebe resposta fundamentada com citacoes |
| POST | `/ingestao` | Corre o pipeline de ingestao para todos os PDFs em `data/documents/` |
| GET | `/documentos` | Lista todos os documentos indexados no Qdrant com chunks e paginas |
| GET | `/health` | Verifica estado do Qdrant e numero de pontos na collection |
| GET | `/audit` | Devolve os registos de auditoria do dia atual |

**Detalhes dos endpoints:**

**POST /consulta**
- Recebe: `ConsultaRequest` (query + tipo_documento opcional)
- Executa o pipeline completo (input guard → retriever → reranker → CRAG → generator → output guard)
- Regista automaticamente no log de auditoria
- Devolve: `ConsultaResponse` (resposta, fontes, metricas)

**POST /ingestao**
- Sem parametros (usa a pasta `data/documents/` por defeito)
- Executa: loader → chunker → embedder → indexer
- Devolve: `IngestaoResponse` (contagens e duracao)

**GET /documentos**
- Consulta o Qdrant via scroll (sem vetores, so payloads)
- Agrega por ficheiro: tipo, numero de chunks, paginas cobertas
- Devolve: `DocumentosListResponse`

**GET /health**
- Testa ligacao ao Qdrant
- Devolve status `"ok"` ou `"degradado"` com mensagem de erro

**GET /audit**
- Le o ficheiro JSONL do dia atual
- Devolve lista de registos com total

---

### Como usar a API

```bash
# Iniciar o servidor
uvicorn src.api.main:app --reload --port 8000

# Swagger UI (browser)
# http://localhost:8000/docs

# Testar via curl
curl http://localhost:8000/health
curl http://localhost:8000/documentos
curl -X POST http://localhost:8000/consulta -H "Content-Type: application/json" -d '{"query": "O que e o Brufen?"}'
```

---

## Testes da API

### Teste do endpoint /health
```json
{
    "status": "ok",
    "qdrant": "conectado",
    "collection": "farmacos",
    "total_pontos": 31
}
```

### Teste do endpoint /documentos
```json
{
    "documentos": [
        {"ficheiro": "brufen.pdf", "tipo_documento": "monografia", "total_chunks": 18, "paginas": [1,2,...,16]},
        {"ficheiro": "brufen_folheto.pdf", "tipo_documento": "bula", "total_chunks": 13, "paginas": [1,2,...,13]}
    ],
    "total_documentos": 2,
    "total_chunks": 31
}
```

### Teste do endpoint /consulta
- Query: "O que e o Brufen?"
- Resposta com citacoes de fontes (brufen.pdf p.1, brufen_folheto.pdf p.1)
- Contexto suficiente: true
- Fontes: 3 (bula p.1, monografia p.1, monografia p.2)
- Auditoria registada automaticamente com timestamp e IP

---

## Outras alteracoes

### requirements.txt (atualizado)
Adicionados:
- `anthropic` — SDK para chamadas ao Claude
- `pytest` — framework de testes
- `numpy<2.0` — necessario no `requirements.txt` para evitar bloqueio de DLL no Windows

### .gitignore (atualizado)
Adicionado:
- `tests/reports/` — relatorios HTML gerados pelo pytest

### config.py
- `load_dotenv()` alterado para `load_dotenv(override=True)` — garante que o `.env` tem prioridade sobre variaveis de ambiente do sistema

### notas.md (atualizado)
Adicionada seccao com comandos da API.

---

## Estado da Implementacao (atualizado)

| Fase | Estado |
|---|---|
| Fase 1 — Ambiente e infraestrutura | ✅ Completo |
| Fase 2 — Pipeline de ingestao | ✅ Completo |
| Fase 3 — Pipeline de consulta | ✅ Completo |
| Fase 4 — API REST | ✅ Completo |
| Testes unitarios e integracao | ✅ 66/66 a passar |

---

## Estrutura de ficheiros (atualizada)

```
src/
├── __init__.py
├── config.py
├── ingestion/
│   ├── __init__.py
│   ├── loader.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── indexer.py
│   └── pipeline.py
├── query/
│   ├── __init__.py
│   ├── retriever.py
│   ├── reranker.py
│   ├── crag.py
│   ├── generator.py
│   ├── prompt.py
│   └── pipeline.py
├── guardrails/
│   ├── __init__.py
│   ├── input_guard.py
│   └── output_guard.py
└── api/
    ├── __init__.py
    ├── main.py           # FastAPI app (5 endpoints)
    ├── models.py          # Schemas Pydantic
    └── audit.py           # Registo de auditoria (JSONL)

tests/
├── __init__.py
├── test_loader.py
├── test_chunker.py
├── test_indexer.py
├── test_input_guard.py
├── test_output_guard.py
├── test_retriever.py
├── test_pipeline.py
└── reports/              # Relatorios HTML (gitignored)

data/
├── documents/
│   ├── bulas/
│   ├── monografias/
│   ├── guidelines/
│   └── normas/
└── audit/                # Logs de auditoria (JSONL por dia)
```

---

## Proximos passos

- **Interface web** — Streamlit ou frontend simples para interacao visual (alternativa ao Swagger UI)
- **Docker Compose** — containerizar app + Qdrant para deployment
- **Deployment via Coolify** — documentar em Cap. 4.3.4
- **Avaliacao RAGAS** — dataset de teste + metricas (Cap. 5)
- **Relatorio** — escrever capitulos 4.3.2, 4.3.3, 4.3.4, 5 e 6
