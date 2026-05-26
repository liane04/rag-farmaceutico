# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pharmaceutical decision-support RAG system built as a final-year Computer Science project at UTAD. Ingests Portuguese pharmaceutical PDFs (bulas, monografias, guidelines, normas INFARMED) and answers clinical questions in natural language with explicit source citations.

**Stack:** LangChain · Gemini Embedding 2 (`gemini-embedding-2-preview`, 3072 dims) · Claude (`claude-sonnet-4-6`) · Qdrant · FastAPI · SQLite · Docker

**Python requirement:** 3.12 or 3.13 only. Python 3.14+ is incompatible with Pydantic V1 used by LangChain.

## Environment Setup

Create `.env` at repo root:
```
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=...
QDRANT_HOST=localhost
QDRANT_PORT=6333
JWT_SECRET_KEY=...
SEED_ADMIN_PASSWORD=...
SEED_FARMACEUTICO_PASSWORD=...
```

Start Qdrant:
```bash
docker start qdrant
# or full stack:
docker compose up --build -d
```

Run the API:
```bash
uvicorn src.api.main:app --reload --port 8000
```

## Commands

```bash
# Run all unit tests (no external services needed)
python -m pytest tests/ -v

# Run integration tests (requires Qdrant + API keys)
python -m pytest tests/ -v -m integration

# Run a single test file
python -m pytest tests/test_retriever.py -v

# Run the query pipeline from CLI
python -m src.query.pipeline "Quais são os efeitos secundários do ibuprofeno?"
python -m src.query.pipeline "..." --tipo bula

# Run the ingestion pipeline from CLI
python -m src.ingestion.pipeline --pasta data/documents
python -m src.ingestion.pipeline --ficheiro data/documents/bulas/brufen.pdf --tipo bula
```

## Architecture

### Ingestion pipeline (`src/ingestion/`)
Sequential 4-step pipeline: `loader.py` (PDF → LangChain Documents via PyMuPDF/pdfplumber) → `chunker.py` (RecursiveCharacterTextSplitter, 4000 chars / 800 overlap) → `embedder.py` (Gemini Embedding 2) → `indexer.py` (Qdrant upsert). Each document chunk carries metadata: `ficheiro`, `pagina`, `tipo_documento`. Entry point: `pipeline.py`.

### Query pipeline (`src/query/`)
6-step pipeline orchestrated in `pipeline.py`:
1. **Input guard** (`guardrails/input_guard.py`) — rejects off-topic queries
2. **Contextual reformulation** (`reformulator.py`) — rewrites query as standalone when conversation history is present
3. **Hybrid retrieval** (`retriever.py`) — Qdrant semantic search, `RETRIEVAL_TOP_K=7`
4. **Reranker** (`reranker.py`) — LLM-as-Judge narrows to `RERANK_TOP_N=3`
5. **CRAG** (`crag.py`) — evaluates context sufficiency; if top reranker score ≥ `SKIP_CRAG_THRESHOLD=0.85`, CRAG is skipped entirely; otherwise may reformulate and re-retrieve (max 2 attempts)
6. **Generator** (`generator.py`) — Claude generates the answer; `gerar_resposta_stream` yields SSE tokens
7. **Output guard** (`guardrails/output_guard.py`) — faithfulness check; flags below `FAITHFULNESS_THRESHOLD=0.85`

Two public functions: `consultar()` (sync, returns `RespostaRAG`) and `consultar_stream()` (generator, yields SSE event dicts: `meta` → `token` → `done`/`error`).

### API (`src/api/`)
FastAPI app (`main.py`) with JWT auth. All endpoints except `/auth/login` require a Bearer token. Key endpoints:
- `POST /consulta` — sync RAG query
- `POST /consulta/stream` — SSE streaming RAG query
- `POST /ingestao` — admin: re-ingest all PDFs in `data/documents/`
- `POST /upload` — admin: upload and ingest a single PDF
- `GET /documentos` — list indexed documents
- `GET /ficheiros/{tipo}/{nome}` — serve original PDF (path traversal protection in place)
- `GET /audit` — admin: full audit log
- `GET /historico` — per-user query history

Serves the SPA at `/` from `src/api/static/index.html`.

### Auth (`src/auth/`)
SQLite database at `data/auth.db`. Two roles: `farmaceutico` and `admin`. Only admins can trigger ingestion, upload, and view full audit logs. JWT tokens expire after 8h (configurable via `JWT_EXPIRA_MINUTOS`). Seed accounts are created from env vars on first startup (`seed.py` called via `lifespan`).

### Documents
PDFs go in `data/documents/{bulas,monografias,guidelines,normas}/`. The subfolder name determines `tipo_documento` metadata. Audit logs are stored in `data/audit/` as JSONL.

## Key Configuration (`src/config.py`)

| Constant | Default | Purpose |
|---|---|---|
| `RETRIEVAL_TOP_K` | 7 | Chunks fetched before reranking |
| `RERANK_TOP_N` | 3 | Chunks after LLM reranker |
| `SKIP_CRAG_THRESHOLD` | 0.85 | Skip CRAG if top reranker score ≥ this |
| `FAITHFULNESS_THRESHOLD` | 0.85 | Flag output if faithfulness < this |
| `RELEVANCE_THRESHOLD` | 0.80 | CRAG considers context sufficient if ≥ this |

## Testing Notes

Tests in `tests/` are split: unit tests run without any external services; tests marked `@pytest.mark.integration` require a running Qdrant and valid API keys. The `pytest.ini` defines the `integration` marker.
