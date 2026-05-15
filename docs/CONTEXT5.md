# CONTEXT5.md — Pos-Fase 4: Docker, refinamentos do pipeline e retoques na UI

## Snapshot no fim do CONTEXT4

- Fase 1 a 4 completas, 66 testes a passar
- API com 5 endpoints (`/consulta`, `/ingestao`, `/documentos`, `/health`, `/audit`)
- `GENERATIVE_MODEL = "claude-sonnet-4-5"` em todas as chamadas LLM
- Sem Dockerfile nem docker-compose
- Frontend inline num so `index.html`
- 2 PDFs ingeridos: `brufen.pdf` (monografia) + `brufen_folheto.pdf` (bula)

Este documento cobre os 5 commits feitos depois disso (13/abril a 2/maio).

---

## `71183fb` — correcoes (13/abr)

### Containerizacao adicionada
- **`Dockerfile`** novo (Python 3.11-slim, libmupdf-dev, copia src/ e data/, expoe 8000, corre uvicorn)
- **`docker-compose.yml`** novo — sobe Qdrant + API juntos. `QDRANT_HOST=qdrant` (DNS interno do Docker)
- **`.dockerignore`** novo
- `docs/notas.md` atualizado com comandos `docker compose up --build`, logs, down -v, etc.

### API: novo endpoint `/upload`
`POST /upload` (multipart) — recebe um PDF + `tipo_documento` no form, valida tipo (bula/monografia/guideline/norma), grava na subpasta correta, e corre o pipeline de ingestao desse ficheiro individual. Em caso de erro, apaga o ficheiro guardado.

### API: ficheiros estaticos
- Mount de `/static` → `src/api/static/`
- Adicionados `favicon.ico` e `logo.png`
- `index.html` ja existia mas cresceu (+139 linhas com a UI)

### Tentativa Claude → Gemini Flash (revertida 10 dias depois)
**Toda a stack LLM migrada para `gemini-2.0-flash`** para poupar tokens:
- `src/query/reranker.py`
- `src/query/crag.py`
- `src/query/generator.py`
- `src/guardrails/input_guard.py`
- `src/guardrails/output_guard.py`

O codigo Claude original ficou em comentarios marcados `[CLAUDE]`. `GENERATIVE_MODEL: claude-sonnet-4-5 → gemini-2.0-flash`.

---

## `3cf2632` — cooreçoes 2 (13/abr)

Pequena correcao ao Docker Compose:
- `QDRANT_HOST=qdrant` → `host.docker.internal` (com `extra_hosts: host-gateway`)
- Motivo: evitar problemas de resolucao de nome quando a API corre fora do compose

README e `notas.md` ajustados para refletir as duas formas de correr (manual vs compose).

---

## `cc181d4` — correçao embedding (23/abr) — commit grande

### Chunker reescrito (cross-page)
**Antes:** um split independente por pagina. O overlap ficava preso dentro da pagina, partindo seccoes que atravessavam fronteiras.

**Agora:** concatena todas as paginas num so texto, faz UM split global, e mapeia cada chunk de volta as paginas de origem.

Cada `Chunk` ganha novo campo `paginas: list[int]` (todas as paginas que cobre) alem do `pagina` (a primeira). `_encontrar_paginas()` faz o mapping.

### Embedder com retry e fallback
**Antes:** batch de 50, sem retry. Falhava com o `gemini-embedding-2-preview` (rate limits restritivos).

**Agora:**
- `BATCH_SIZE: 50 → 5`
- `MAX_RETRIES = 3` com backoff exponencial
- Se um lote falhar OU devolver numero errado de embeddings, faz fallback para `_embeber_individual()` (chunk a chunk com retry)

### config.py
- `EMBEDDING_MODEL`: `"models/gemini-embedding-2-preview"` → `"gemini-embedding-2-preview"` (sem prefixo `models/`)
- `GENERATIVE_MODEL`: `gemini-2.0-flash` → **`claude-sonnet-4-6`** — reverte a migracao Gemini do `71183fb`, e bumpa para a nova versao do Sonnet

### Reversao LLM Gemini → Claude (parcial)
Reverte para Claude em `reranker.py`, `crag.py`, `generator.py`. Comentarios `[CLAUDE]` mortos removidos. **`input_guard.py` e `output_guard.py` ficam ainda em Gemini neste commit** — completados no commit seguinte.

### Outras coisas
- `data/documents/monografias/brufen.pdf` apagado — fica so a bula (`brufen_folheto.pdf`)
- `index.html` cresce +946 linhas (UI mais rica, antes da separacao em ficheiros)
- `requirements.txt` ganha `google-generativeai`
- `input_guard.py`: pequena melhoria `.replace("*", "")` na resposta do LLM

---

## `2ca27bd` — b (23/abr, ao fim do dia)

Termina a reversao iniciada em `cc181d4`:
- `input_guard.py` e `output_guard.py` revertidos para Claude. `[CLAUDE]` removidos.
- `temperature=0` adicionado na chamada do `input_guard`

Tambem:
- `.claude/settings.local.json` adicionado
- Audit log `2026-04-23.jsonl` gerado pelos testes manuais
- Testes adaptados ao desaparecimento do `brufen.pdf`:
  - `test_chunker.py::test_preserva_ficheiros_diferentes` agora usa um `DocumentoExtraido` sintetico em vez de carregar `brufen.pdf`
  - `test_loader.py::test_infere_tipo_monografia` substituido por `test_infere_tipo_pela_pasta` (usa `tmp_path` com PDF copiado)

---

## `b8cefb8` — melhorias (2/maio)

### Frontend separado em 3 ficheiros
Antes tudo era inline em `index.html` (1257 linhas). Agora:
- `index.html` (estrutura)
- `src/api/static/app.js` (~326 linhas — logica)
- `src/api/static/style.css` (~925 linhas — estilos)

### Analise externa adicionada
**`docs/melhorias_antigravity.md`** — analise feita pelo Antigravity a 02/05/2026 com 10 melhorias por prioridade:

**Alta:**
1. `payload.pop("texto")` em `retriever.py:110` e destrutivo — mudar para `.get()`
2. README com notas pessoais misturadas — mover para `NOTAS_PESSOAIS.md`

**Media:**
3. `reranker.py:92` muta o chunk original ao escrever `chunk.score`
4. `Anthropic(api_key=...)` recriado em cada chamada (crag/reranker/generator/output_guard) — usar singleton
5. Testes de integracao sem mocks (consomem tokens reais)
6. Tokenizacao BM25 em `_texto_para_sparse` muito basica — considerar `rank_bm25`

**Baixa:**
7. `print()` → `logging` estruturado
8. Rate limiting na API (slowapi)
9. Cache de embeddings de queries
10. Versionamento de modelos nos logs de auditoria

**Nenhum dos 10 itens foi implementado ainda.**

### Audit log `2026-04-24.jsonl` adicionado
Testes manuais antigos commitados.

---

## Estado real (12/maio/2026)

| Componente | Valor atual |
|---|---|
| `EMBEDDING_MODEL` | `gemini-embedding-2-preview` (so embeddings) |
| `GENERATIVE_MODEL` | `claude-sonnet-4-6` (toda a stack LLM) |
| Python suportado | 3.12 ou 3.13 (3.14+ incompativel com Pydantic V1) |
| Chunker | Cross-page com mapping de chunks → paginas |
| Embedder | Batch 5 + retry + fallback individual |
| API endpoints | 6 (`/consulta`, `/ingestao`, `/upload`, `/documentos`, `/health`, `/audit`) |
| Deployment | `docker compose up --build` (compose) ou uvicorn local |
| Frontend | Separado em `index.html` + `app.js` + `style.css` (ainda em iteracao) |
| Documentos indexados | 1 bula (`brufen_folheto.pdf`) |
| Suite de testes | 7 ficheiros (`test_chunker.py` e `test_loader.py` adaptados a falta da monografia) |

### Estrutura de ficheiros adicionada desde o CONTEXT4

```
Dockerfile
.dockerignore
docker-compose.yml
docs/
└── melhorias_antigravity.md   <- novo
src/api/static/
├── app.js                      <- novo (extraido de index.html)
├── style.css                   <- novo (extraido de index.html)
├── favicon.ico                 <- novo
└── logo.png                    <- novo
```

### Memory atualizada
`memory/project_crag_llm_strategy.md` documenta agora que Claude e o LLM unico da stack (Gemini so para embeddings). A estrategia "Gemini para CRAG" da memory antiga ficou obsoleta com a reversao de `cc181d4` + `2ca27bd`.

---

## Pontos abertos / proximos passos

- **Frontend ainda em iteracao** — nao tratar a estrutura atual como definitiva
- 10 melhorias do Antigravity por implementar
- RNF01 (pipeline ≤10s) ainda nao cumprido — pipeline atual demora ~35-50s (5 chamadas LLM)
- Re-ingerir uma monografia (pasta `monografias/` esta vazia desde `cc181d4`)
- Avaliacao RAGAS (Cap. 5 do relatorio)
- Deployment Coolify (Cap. 4.3.4)
