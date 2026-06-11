# CONTEXT9.md — Deploy em producao (Coolify) + switch LLM online/local (Claude/Ollama)

> Data: 2026-06-09. Cobre tudo o que aconteceu desde o fim do CONTEXT8
> (trabalho de login/perfis, depois committed em `bcf51ed`): o commit dessa
> fase, o **deploy para producao** no Coolify, o polimento de UI, e — nesta
> sessao — a **validacao e commit** da feature de switch LLM (online/local)
> que ja estava no disco por commitar, mais o **fix do QDRANT_HOST** no Docker.
> Atualizado a 2026-06-10 com a **Parte 4**: amend/force-push (remocao da
> atribuicao ao Claude) + deploy, README reescrito, e **modo local tornado
> viavel** (qwen2.5:3b-instruct + format=json).

## Snapshot no fim do CONTEXT8

- Trabalho de auth/perfis/frontend modular concluido mas **uncommitted**.
- App inteira gateada por JWT; 2 papeis (`admin`, `farmaceutico`).
- Ultimo commit no `main` era `b91ebb2` (streaming SSE / CONTEXT7).
- Fase 4 do plano de login (testes + documentacao + relatorio) em aberto.

---

## Parte 1 — Commit do login + deploy para producao (2026-05-25 a 05-29)

> **Provenencia:** reconstruido a partir do historico git e do estado atual
> dos ficheiros de deploy. Estes commits nao tiveram sessao de CONTEXT a
> documenta-los em detalhe; o que segue e factual (mensagens de commit +
> ficheiros tocados + leitura do `docker-compose.yml`/`Dockerfile`/`.env.example`).

| Commit | Data | O que |
|---|---|---|
| `bcf51ed` | 05-25 | **sistema de login e perfis** — commit de toda a fase do CONTEXT8 |
| `3afdc07` | 05-26 | fix deploy Coolify: seed, healthcheck, dockerignore; **`CLAUDE.md` criado** (+107 linhas) |
| `e9daee4` | 05-26 | seed atualiza password se a conta ja existe (`atualizar_password_utilizador` em `db.py`) |
| `1476905` | 05-27 | env vars obrigatorias, healthcheck, **`.env.example` criado** (+14) |
| `c165f80` | 05-27 | **montar `.env` no container** (`./.env:/app/.env:ro`) p/ garantir passwords corretas |
| `4f77049` | 05-29 | polimento de UI: **`dropdown.js` novo** (+101), `chat.js`, `admin.js`, `style.css` (+318), favicon/logo |

### A app foi para producao

- **URL:** https://prj-rag-ld.teclab.pt/ — Coolify, **auto-deploy on push** ao `main`.
- **`docker-compose.yml`:** dois servicos — `qdrant` (imagem oficial, volume `qdrant_data`) e `api` (build local). A `api` leva `env_file: .env` (opcional), `environment: QDRANT_HOST=qdrant` + `QDRANT_PORT`, volumes `./data:/app/data` e `./.env:/app/.env:ro`, `depends_on: qdrant`, `restart: unless-stopped`.
- **`Dockerfile`:** `python:3.12-slim`, `pip install -r requirements.txt`, `COPY src/`, cria as pastas de `data/`, `HEALTHCHECK` que faz GET a `/health`, `CMD uvicorn ... --host 0.0.0.0 --port 8000`.
- **`.env.example`:** chaves Google/Anthropic, `QDRANT_HOST=localhost`, `JWT_SECRET_KEY`, `SEED_ADMIN_PASSWORD`, `SEED_FARMACEUTICO_PASSWORD`.
- **Seed idempotente:** ao arrancar, cria/atualiza `admin` e `farmaceutico` com as passwords do `.env` (visto nos logs do container).

> **Nota de governanca (memoria):** infra/deploy e alcada do orientador de
> estagio (Ricardo Costa, Teclab). Pushes ao `main` vao directos para
> producao. Alteracoes a config de deploy devem passar por ele primeiro.

### Polimento de UI (`4f77049`)

`dropdown.js` novo (componente de dropdown reutilizavel), reescrita parcial do
`chat.js` e `admin.js`, +318 linhas de `style.css`, favicon novo e `logo-dark.png`.
(Detalhe fino nao documentado — fora do scope desta sessao.)

---

## Parte 2 — Feature de switch LLM (pre-existente no disco, uncommitted no inicio desta sessao)

Tal como a Fase 1+2 do CONTEXT8, este trabalho **ja estava no disco por
commitar** quando esta sessao comecou — construido numa sessao nao documentada
entre `4f77049` (05-29) e hoje. Sumario das pecas (revistas via diff nesta sessao):

### Objectivo

Permitir ao admin alternar **toda a stack de query/guardrails** entre:
- **`online`** (default): Claude `claude-sonnet-4-6` via SDK `anthropic` — qualidade maxima.
- **`local`**: Ollama (modelo via `OLLAMA_MODEL`) via `langchain-ollama` — privacidade/RGPD.

O modo e **persistido em SQLite** e **re-lido a cada chamada** (troca sem reiniciar o servico).

### `src/config.py`

```python
OLLAMA_HOST      = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
LLM_MODE_DEFAULT = os.getenv("LLM_MODE_DEFAULT", "online")
```

### `src/llm_client.py` (refactor grande, +182 linhas)

- `obter_modo_llm()` / `definir_modo_llm(modo)` — le/escreve a definicao `llm_mode` na BD (import preguicoso de `db.py` para evitar ciclo).
- `_obter_cliente_anthropic()` / `_obter_cliente_ollama(temperature)` — clientes lazy partilhados; o `ChatOllama` recria-se quando muda a temperatura.
- **`chamar_llm(prompt, system, max_tokens, temperature) -> str`** e **`stream_llm(...) -> Iterator[str]`** — interface unificada que abstrai o provider activo.
- `obter_cliente()` mantida como **[DESCONTINUADA]** (devolve sempre o cliente Anthropic) para retro-compatibilidade.

### `src/auth/db.py`

Nova tabela **`definicoes`** (`chave TEXT PK`, `valor TEXT`, `alterado_em TEXT`) + funcoes `obter_definicao(chave, default)` e `definir_definicao(chave, valor)` (upsert via `ON CONFLICT`). Criada no `inicializar_bd()`.

### `src/api/main.py`

Dois endpoints novos, ambos `requer_admin`:
- `GET /admin/llm-mode` -> `{modo, modelo_online, modelo_local}`.
- `POST /admin/llm-mode` -> valida `{"modo": "online"|"local"}` (400 se invalido) e persiste.

### Frontend

- `js/admin.js`: **`renderDefinicoes(container)`** — settings-card com toggle Online/Local, `loadLlmMode()` (GET), `toggleLlmMode()` (POST com revert em erro), `_renderLlmMode()`.
- `js/main.js`: nova tab **"Definicoes"** (so admin).

### Os 4 callsites migrados

`reranker.py`, `crag.py`, `generator.py` e `guardrails/output_guard.py` deixaram de chamar `obter_cliente().messages.create(...)` directo e passaram a usar `chamar_llm` / `stream_llm`. (O `crag.py` perdeu o helper local `_chamar_llm`.)

### Dependencia nova

`langchain-ollama` em `requirements.txt`.

---

## Parte 3 — Esta sessao (2026-06-09): validacao em Docker, fix do Qdrant, commit

### 3.1 Revisao + teste local da feature

- Ambiente: **`langchain-ollama 1.1.0`** instalado; **Ollama a correr** com `llama3.2:1b` puxado.
- Teste directo de `chamar_llm` nos dois modos -> ambos devolveram resposta.
- Teste de `stream_llm` em local -> 33 pedacos, token-a-token (o caminho que o chat usa).
- Round-trip da definicao em SQLite OK.

### 3.2 Teste em Docker (o mais proximo de producao)

- `docker compose build` + `up -d` -> apanha o codigo por commitar + `langchain-ollama`. API arranca **healthy**.
- **Prova de rede:** de dentro do container `rag_api`, `host.docker.internal:11434` alcanca o Ollama do Windows. (Para o modo local funcionar no Docker o `OLLAMA_HOST` tem de apontar para `host.docker.internal` — posto **so no `.env` local**, gitignored, nao commitado.)
- **Modo online ponta-a-ponta:** `/consulta "efeitos secundarios do ibuprofeno"` devolveu resposta real, formatada e **citada** (`brufen_folheto.pdf`, p.10), `contexto_suficiente=True`, **fidelidade 0.98**. Pipeline RAG completo a funcionar no Docker.

### 3.3 Bug encontrado: QDRANT_HOST errado no Docker (fix Opcao A)

- **Sintoma:** `/health` = `"degradado"`, `qdrant: Connection refused`.
- **Causa:** [`config.py`] chamava `load_dotenv(override=True)`. O `docker-compose.yml` injecta `QDRANT_HOST=qdrant`, mas o `.env` montado tem `QDRANT_HOST=localhost`; o `override=True` fazia o `.env` **ganhar**, e a API procurava o Qdrant em `localhost` **dentro do proprio container**.
- **Confirmado empiricamente:** dentro do container `config.QDRANT_HOST=localhost`, mas `qdrant:6333` respondia **HTTP 200** (servico bom; config errada).
- **Fix:** `load_dotenv()` (override=False, default) — variaveis reais do ambiente passam a ter precedencia sobre o `.env`. Apos rebuild: `/health` = `ok`, `qdrant: conectado`, 12 chunks. `bcf51ed`..hoje a linha era do proprio inicio do projeto (`a090edb1`, 04-10); nada dependia dela.

### 3.4 Modo local **nao e viavel** com o `llama3.2:1b`

A troca funciona, mas uma `/consulta` real em local **falhou** (timeout). Os logs revelaram dois problemas que se somam:
1. **Formato:** o `1b` nao devolve o JSON que o reranker e o CRAG pedem -> `[reranker] Falha ao parsear` / `[crag] Falha ao parsear avaliacao. A assumir relevante` (confianca 0.50) -> entra em **loop de re-retrieval**. Os safeguards degradam-se em silencio (incluindo o output_guard de fidelidade — critico num sistema farmaceutico).
2. **Desempenho:** 4+ chamadas LLM em CPU saturam o worker unico do uvicorn; a `/consulta` passou dos **120s** e o `/health` ficou em **HTTP 000**. Foi preciso reiniciar o container.

> Conclusao: o **mecanismo** do switch esta pronto e validado; o **modo local
> como opcao utilizavel** nao esta. Precisaria de modelo `>=7-8B` que siga JSON
> (ex.: `llama3.1:8b`, `qwen2.5:7b-instruct`), idealmente GPU, e/ou adaptar a
> pipeline em local (saltar/simplificar reranker e CRAG, parsing tolerante,
> chamadas nao-bloqueantes).

### 3.5 Commit

- **`014d2d7`** — `feat: switch LLM online/local (Claude/Ollama) + fix QDRANT_HOST no Docker` · **12 ficheiros, +575/-63**.
- Inclui a feature LLM **e** o fix do Qdrant. Ficou **so no `main` local** (`ahead 1`, **sem push** -> producao intacta).
- Branch de trabalho `fix/qdrant-override-docker` criada e apagada.
- **Deixados de fora de proposito:** `.claude/settings.local.json` (config local da ferramenta) e `.env` (gitignored; o `OLLAMA_HOST` local fica so na maquina).
- Modo persistido na BD posto em **`online`** no fim da sessao.

---

## Ficheiros do commit `014d2d7` (apos amend: `320a863`)

```
M  requirements.txt                 <- + langchain-ollama
M  src/config.py                    <- + OLLAMA_*/LLM_MODE_DEFAULT; load_dotenv() override=False (fix Qdrant)
M  src/llm_client.py                <- multi-provider: chamar_llm/stream_llm, obter/definir_modo_llm
M  src/auth/db.py                   <- tabela 'definicoes' + obter/definir_definicao
M  src/api/main.py                  <- GET/POST /admin/llm-mode
M  src/api/static/js/admin.js       <- renderDefinicoes + toggle
M  src/api/static/js/main.js        <- tab "Definicoes" (admin)
M  src/api/static/style.css         <- estilos do settings-card/toggle
M  src/guardrails/output_guard.py   <- migrado para chamar_llm
M  src/query/crag.py                <- migrado para chamar_llm
M  src/query/generator.py           <- migrado para chamar_llm/stream_llm
M  src/query/reranker.py            <- migrado para chamar_llm
```

---

## Validacoes feitas

- `chamar_llm` online (Claude) e local (Ollama) — local e em Docker.
- `stream_llm` local — token-a-token.
- Networking container -> `host.docker.internal:11434`.
- `/health` antes (degradado) e depois (ok, qdrant conectado, 12 chunks) do fix.
- Login admin + `GET/POST /admin/llm-mode` via HTTP.
- `/consulta` real em **online** — resposta citada, fidelidade 0.98.

**Nao corridos / por validar (estado no fim da Parte 3; ver Parte 4):**
- Clicar no toggle no browser ponta-a-ponta — *resolvido na Parte 4 (Liane clicou; POSTs 200 nos logs)*.
- `/consulta` real em **local** (falha por timeout/JSON com o `1b`) — *resolvido na Parte 4 (qwen2.5:3b)*.
- Suite de testes do `llm_client` (nao existe; ver proximos passos).
- Se **producao** sofre do mesmo `override` (depende do `QDRANT_HOST` no `.env` montado no Coolify).

---

## Parte 4 — Continuacao (2026-06-09/10): push + deploy, README, modo local viavel

### 4.1 Amend do commit, remocao da atribuicao, push (e deploy)

- A Liane deu push do `014d2d7` e detectou o trailer `Co-Authored-By: Claude`
  na mensagem. O commit foi **amendado para `320a863`** (mesmo conteudo, so a
  mensagem sem o trailer) e **force-pushed** para os dois remotes — `origin`
  (github.com/liane04/rag-farmaceutico) e `trabalho` (github.com/teclab-ai/PRJ-RAG-LD)
  — em ambos confirmando primeiro que o HEAD remoto era exactamente o `014d2d7`.
- Consequencia: o push a `main` do repo de trabalho **disparou o auto-deploy**
  — a feature de switch LLM + o fix do QDRANT_HOST **estao em producao**.
- Prevencao: `"includeCoAuthoredBy": false` adicionado as settings do Claude
  Code, locais (`.claude/settings.local.json`) e **globais** (`~/.claude/settings.json`)
  — nenhum commit futuro leva atribuicao, em nenhum projeto.
- Pendente: avisar o Ricardo do force-push (historia reescrita no repo de
  trabalho) e confirmar a saude de producao pos-deploy.

### 4.2 README reescrito

Modelo corrigido ("Claude 3.5 Sonnet" → Claude Sonnet 4.6 / Ollama), seccao de
funcionalidades (login/perfis, streaming, citacoes, switch LLM, auditoria),
`.env` completo (JWT_SECRET_KEY, SEED_*, OLLAMA_*), arranque (API local vs
Docker), seed de contas, ingestao, modo de geracao com exemplo curl do
`/admin/llm-mode`, e testes. Removidas as notas soltas do fim.

### 4.3 Modo local tornado viavel (qwen2.5:3b-instruct + format=json)

A sessao de 06-10 atacou a inviabilidade diagnosticada na Parte 3. Quatro
problemas encontrados e corrigidos, por ordem de descoberta:

| # | Problema | Fix |
|---|---|---|
| 1 | **`input_guard` e `reformulator` nunca foram migrados** — chamavam `obter_cliente()` (Claude directo). Em modo local, o input_guard rebentava com `APIConnectionError` antes de chegar ao retriever. O "switch" so cobria 4 dos 6 callsites. | Migrados para `chamar_llm` → **6/6 callsites** passam pelo switch; em local nenhum toca no Anthropic. |
| 2 | Modelos locais nao devolviam JSON parseavel nos passos estruturados. | `chamar_llm` ganhou **`force_json: bool`** — em modo local activa `format="json"` do Ollama (saida JSON garantida via grammar); em online e ignorado (Claude ja segue o prompt). Activo no reranker, CRAG-avaliacao e fidelidade. |
| 3 | Com `format=json`, o qwen devolvia **um objeto unico** em vez do array de avaliacoes do reranker (`{"indice":0,...}` so para o 1o excerto). | Prompt do reranker passou a pedir envelope **`{"avaliacoes": [...]}`**; parsing robusto (desembrulha dict, aceita objeto unico, filtra nao-dicts); o log do fallback agora inclui o output cru truncado. |
| 4 | Com o input real (7 chunks × 4000 chars ≈ 28K), o qwen **descarrilava** — ignorava a tarefa e inventava outra em ingles (`{"instructions":[...]}`), JSON invalido. | Em modo local o reranker trunca cada excerto a **700 chars** (`MAX_DOC_CHARS_LOCAL`); online mantem os 4000. O inicio do chunk chega para julgar relevancia. |

Mais: **modelo default trocado** `llama3.2:1b` → **`qwen2.5:3b-instruct`**
(1.9 GB, puxado via `ollama pull`) em `config.py`.

### 4.4 Validacao da Parte 4

- **venv local, modo local:** pipeline completo OK — reranker **sem fallback**,
  CRAG `confianca=0.90`, fidelidade 0.5–0.6, resposta citada (`brufen_folheto.pdf`).
- **Regressao do modo online:** fidelidade **0.97**, reranker sem fallback —
  as mudancas (prompt do reranker, migracao dos 2 callsites) nao partiram nada.
- **Docker (apos rebuild pela Liane):** `/consulta` real em modo local via API
  → resposta organizada e citada, `contexto_suficiente=True`, **6m20s** em CPU;
  logs do container **sem avisos de parsing**. UI: a Liane clicou o toggle no
  browser e usou o chat em streaming (`POST /admin/llm-mode` e
  `POST /consulta/stream` com 200 nos logs do uvicorn).

### 4.5 Trade-offs honestos do modo local (para o relatorio)

- **Fidelidade ~0.5–0.6** (vs ~0.97 do Claude) → o output_guard anexa a "NOTA
  DE QUALIDADE" — guardrail a funcionar como desenhado, mas qualidade inferior.
- **~6 min/consulta em CPU** — viavel para demo/prova de conceito de
  privacidade; uso real exigiria GPU (e/ou modelo maior).
- Durante a consulta local, o **worker unico do uvicorn fica ocupado** (outros
  pedidos esperam). Melhoria futura: mais workers ou chamadas nao-bloqueantes.
- Os **embeddings continuam Gemini** — o modo local nao e 100% offline; a
  query ainda passa pela API do Google no retrieval. Documentar como limitacao.

### Ficheiros tocados na Parte 4 (uncommitted no fim)

```
M  src/config.py                    <- OLLAMA_MODEL default: qwen2.5:3b-instruct
M  src/llm_client.py                <- chamar_llm(force_json=...) + bind(format="json")
M  src/guardrails/input_guard.py    <- migrado para chamar_llm (era Claude directo)
M  src/query/reformulator.py        <- migrado para chamar_llm (era Claude directo)
M  src/query/reranker.py            <- prompt-envelope, parsing robusto, truncagem local 700
M  src/query/crag.py                <- force_json=True na avaliacao
M  src/guardrails/output_guard.py   <- force_json=True na fidelidade
M  README.md                        <- reescrito (4.2)
```

---

## Pontos abertos / proximos passos

### Sobre esta sessao (estado apos a Parte 4)

1. ~~Push do `014d2d7`~~ **FEITO** (como `320a863`, ver 4.1) — o push acabou
   por acontecer antes da conversa com o Ricardo. Pendente: **avisar o Ricardo**
   do force-push e do deploy, e **confirmar a saude de producao**.
2. **Verificar se producao tem/tinha o bug do Qdrant** — o fix ja esta deployed;
   confirmar que o retrieval em producao funciona (e o `QDRANT_HOST` no Coolify).
3. ~~Modo local: trocar o modelo / aligeirar pipeline~~ **FEITO na Parte 4**
   (qwen2.5:3b + format=json + truncagem). Melhoria futura: GPU e/ou modelo maior.
4. **Commit das mudancas da Parte 4** — 8 ficheiros uncommitted (ver lista na 4.3).
5. **Back-documentar no relatorio** a feature de switch LLM como requisito novo
   (origem provavel no estagio, a la RF15) — privacidade/RGPD vs. qualidade,
   com os trade-offs medidos da seccao 4.5.
6. **Testes:** `tests/test_llm_client.py` (modo round-trip + valores invalidos,
   `chamar_llm`/`stream_llm`/`force_json` com cliente mockado por provider) e
   `tests/test_auth.py` (Fase 4 do plano de login, herdado do CONTEXT8).

### Herdados de CONTEXTs anteriores (re-verificar)

- Fase 4 do plano de login: `tests/test_auth.py`, README com fluxo de seed/login.
- Mensagens de erro Pydantic em portugues.
- Decisao do LangChain (opcao A vs B do CONTEXT7).
- README possivelmente ainda diz "Claude 3.5 Sonnet".
- Limpeza de disco (bge-reranker / sentence_transformers no venv).

---

## Resumo executivo

- **A app foi para producao** (Coolify, https://prj-rag-ld.teclab.pt/, auto-deploy on push) com fixes de seed/healthcheck/env e montagem do `.env` no container; mais um polimento de UI (`dropdown.js`, `style.css` +318).
- **Feature de switch LLM** (online Claude / local Ollama) **validada e committed** (`014d2d7`): cliente unificado `chamar_llm`/`stream_llm`, modo persistido em SQLite e alternavel pelo admin, endpoints `/admin/llm-mode`, tab "Definicoes", 4 callsites migrados.
- **Bug do Qdrant em Docker corrigido** — `load_dotenv(override=False)` para as variaveis do `docker-compose` ganharem ao `.env`. `/health` passou de "degradado" a "ok"; RAG completo a funcionar em **online** (resposta citada, fidelidade 0.98).
- **Modo local nao e utilizavel com o `llama3.2:1b`** — falha o JSON do reranker/CRAG e bloqueia o worker (timeout). O mecanismo esta pronto; falta um modelo capaz (>=7-8B, GPU) e/ou adaptar a pipeline. **Deixar `online` em producao.**
- ~~Commit so no `main` local, sem push~~ **(superado na Parte 4)** — o commit
  foi amendado para `320a863` (sem atribuicao ao Claude) e **pushed/deployed**
  nos dois remotes; `includeCoAuthoredBy: false` configurado local e globalmente.
- **Parte 4 tornou o modo local viavel:** 6/6 callsites no switch (faltavam
  input_guard e reformulator), `force_json` (format=json do Ollama) nos passos
  estruturados, reranker com prompt-envelope + truncagem local (700 chars), e
  default `qwen2.5:3b-instruct`. Validado ponta-a-ponta no venv e no Docker
  (resposta citada, sem avisos de parsing, ~6m20s em CPU, fidelidade 0.5-0.6
  vs 0.97 online). README reescrito. **Fica por commitar** (8 ficheiros).
