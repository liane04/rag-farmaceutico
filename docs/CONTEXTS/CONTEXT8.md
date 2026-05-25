# CONTEXT8.md — Autenticacao, perfis de utilizador e frontend modular

> Data: 2026-05-25. Cobre tudo o que esta uncommitted no fim desta sessao,
> retomando o estado no fim do CONTEXT7 (commit `b91ebb2`).

## Snapshot no fim do CONTEXT7

- Commit no `main`: `b91ebb2 streaming SSE da geracao + abrir PDF nas fontes`
- Pipeline RAG ponta-a-ponta a funcionar com chat conversacional + streaming
- 13 rotas FastAPI; **API completamente aberta** (sem autenticacao)
- Frontend monolitico em [src/api/static/app.js](src/api/static/app.js) (~610 linhas, sem modulos)
- Auditoria em ficheiros JSONL diarios (`data/audit/audit_YYYY-MM-DD.jsonl`)

A pedido do orientador de estagio (Ricardo Costa, Teclab), entrou no scope um
requisito novo — **autenticacao com perfis de utilizador**. Esta sessao fecha
a fase 3 desse plano e deixa a app inteira gateada por login.

---

## Origem e planeamento

A funcionalidade de login **nao consta da proposta formal** do projeto. Veio
do estagio. Foi criado o documento de trabalho [docs/plano_login_perfis.md](docs/plano_login_perfis.md)
com 4 fases. Resumo:

| Fase | Estado no inicio desta sessao | Estado no fim |
|---|---|---|
| 1 — Fundacao auth (backend) | concluida, uncommitted | concluida, uncommitted |
| 2 — Login + auditoria em BD + historico | concluida, uncommitted | concluida, uncommitted |
| 3 — Frontend + protecao de endpoints | nao iniciada | **concluida nesta sessao**, uncommitted |
| 4 — Testes + documentacao | nao iniciada | nao iniciada |

Acao academica obrigatoria (back-documentar como **RF15 — Autenticacao e
perfis de utilizador** no relatorio, identificando origem no estagio) continua
em aberto. Ver seccoes 1 e 10 do plano.

---

## Fase 1+2 (pre-existente nesta sessao) — recap

O trabalho ja estava no disco quando esta sessao comecou. Sumario das pecas
para o leitor entender o que esta no repo antes de ler a Fase 3:

### Dependencias novas

`bcrypt` e `pyjwt` em [requirements.txt](requirements.txt).

### `src/auth/` (package novo, 5 ficheiros)

| Ficheiro | Responsabilidade |
|---|---|
| [modelos.py](src/auth/modelos.py) | Pydantic: `Utilizador`, `UtilizadorEmBD`, `Token`, `DadosToken`, `RegistoConsulta`. `Papel = Literal["farmaceutico", "admin"]` |
| [db.py](src/auth/db.py) | SQLite. Cria tabelas `utilizadores` e `consultas`. Funcoes `obter_utilizador`, `criar_utilizador`, `inserir_consulta`, `listar_consultas`, `listar_consultas_por_utilizador`. Cada operacao abre/fecha a sua ligacao (multi-thread) |
| [seguranca.py](src/auth/seguranca.py) | `gerar_hash_password` / `verificar_password` (bcrypt). `criar_token` / `descodificar_token` (JWT HS256 com `sub`, `papel`, `exp`). `RuntimeError` se `JWT_SECRET_KEY` nao definida |
| [dependencias.py](src/auth/dependencias.py) | `utilizador_atual` (-> 401) via `OAuth2PasswordBearer`. `requer_admin` (-> 403) |
| [seed.py](src/auth/seed.py) | `python -m src.auth.seed` — idempotente, cria `admin` e `farmaceutico` com passwords do `.env` |

### Tabela `consultas` (substitui o JSONL)

Mesma colunas que o JSONL antigo + `utilizador` e `papel`. Migracao automatica
ao arrancar a API: `lifespan` chama `inicializar_bd()`.

### `src/api/audit.py`

`registar_consulta()` agora escreve via `inserir_consulta()` na SQLite (em
vez de `open(...).write(json.dumps(...))`). Aceita `utilizador` e `papel`
(ambos opcionais; eram None nos pedidos sem auth).

### `src/api/main.py` (alteracoes da Fase 1+2)

- `lifespan` chama `inicializar_bd()` no arranque
- Novos endpoints `POST /auth/login` (OAuth2 password flow) e `GET /auth/me`
- Novo endpoint `GET /historico` — consultas do utilizador autenticado
- `GET /audit` reescrito para ler da SQLite (`listar_consultas()`)

### `src/config.py`

```python
JWT_SECRET_KEY        = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM         = "HS256"
JWT_EXPIRA_MINUTOS    = int(os.getenv("JWT_EXPIRA_MINUTOS", "480"))   # 8h
AUTH_DB_PATH          = ".../data/auth.db"
SEED_ADMIN_PASSWORD        = os.getenv("SEED_ADMIN_PASSWORD")
SEED_FARMACEUTICO_PASSWORD = os.getenv("SEED_FARMACEUTICO_PASSWORD")
```

### `.gitignore`

Acrescentado `data/auth.db` (BD de utilizadores, com hashes).

> **Nota explicita:** a Fase 1+2 deixou os endpoints existentes **sem
> protecao** (intencional — a proteccao ficou para a Fase 3, junto com o
> frontend, para a app nunca ficar partida).

---

## Fase 3 — protecao de endpoints e frontend modular (esta sessao)

### 3.1 Backend — matriz de protecao

[src/auth/dependencias.py](src/auth/dependencias.py): adicionada
**`utilizador_atual_query`** — variante que aceita o token via header
**OU** via query param `?token=...`. Necessaria porque o browser nao envia
o header `Authorization` em `<a href>` ou `<iframe>` — sem este fallback,
clicar numa fonte (`/ficheiros/.../doc.pdf`) daria sempre 401.

[src/api/main.py](src/api/main.py): aplicada a matriz da seccao 3 do plano:

| Endpoint | Dependencia | Notas |
|---|---|---|
| `GET /` (interface), `GET /static/*` | nenhuma | a pagina de login tem de carregar antes de haver token |
| `GET /health` | nenhuma | usado pelo `main.js` para mostrar o status no header |
| `POST /auth/login` | nenhuma | obvio |
| `GET /auth/me` | `utilizador_atual` | ja existia |
| `POST /consulta` | `utilizador_atual` | + `utilizador`/`papel` passados a `registar_consulta` |
| `POST /consulta/stream` | `utilizador_atual` | idem (audit em BackgroundTasks) |
| `GET /documentos` | `utilizador_atual` | |
| `GET /historico` | `utilizador_atual` | filtrado por utilizador no backend |
| `GET /ficheiros/{tipo}/{nome}` | `utilizador_atual_query` | aceita `?token=` |
| `POST /upload` | `requer_admin` | |
| `POST /ingestao` | `requer_admin` | |
| `GET /audit` | `requer_admin` | |

Os endpoints que registam auditoria (`/consulta` e `/consulta/stream`) agora
passam `utilizador.username` e `utilizador.papel` ao `registar_consulta()` —
fecha o trilho de auditoria por utilizador prometido no plano (sec. 5.5).

### 3.2 Frontend — reestruturacao em modulos ES

Eliminado [src/api/static/app.js](src/api/static/app.js) (610 linhas
monoliticas). Substituido pela pasta [src/api/static/js/](src/api/static/js/)
com 6 modulos ES (`<script type="module">`, sem bundler, sem npm):

```
src/api/static/
├── index.html             # shell: #login-view + #app-view
├── style.css              # base partilhada (+ login styles novos)
├── favicon.{ico,png}
├── logo.png
└── js/
    ├── api.js             # fetch + Authorization + 401 + ficheiroUrl()
    ├── auth.js            # login() / logout() / obterUtilizadorAtual()
    ├── chat.js            # vista do chat (partilhada pelos dois papeis)
    ├── admin.js           # renderDocumentos + renderAuditoria
    ├── historico.js       # renderHistorico (consultas do utilizador)
    └── main.js            # entrada: shell + routing por papel
```

> **Decisao:** o plano original sugeria `js/`, `css/`, `assets/` em
> subpastas. Mantida a estrutura plana porque (a) ja so havia 1 CSS e 2
> assets, (b) reduz disrupcao com o resto da app. So a `js/` foi criada.

#### `js/api.js` — transporte HTTP

- `getToken` / `setToken` / `clearToken` em `localStorage['rag_token']`
- `apiFetch(path, options)` — injecta `Authorization: Bearer <token>` e
  trata 401 disparando um `CustomEvent('auth:expired')` no `window`
- Convenience: `apiGet`, `apiPostJson`, `apiPostForm`
- **`ficheiroUrl(tipo, nome, pagina)`** — constroi
  `/ficheiros/{tipo}/{nome}?token={JWT}#page={N}`. Usado pelas tags de
  fontes do chat
- `formatarDetalheErro()` — extraido do antigo `formatErrorDetail` para
  reuso entre modulos

#### `js/auth.js` — login flow

- `login(username, password)` — POST `/auth/login` com
  `application/x-www-form-urlencoded` (OAuth2PasswordRequestForm)
- `obterUtilizadorAtual()` — GET `/auth/me` para descobrir o papel

#### `js/chat.js` — vista do chat (igual para os dois papeis)

Migracao directa do antigo `app.js`:
- `renderChat(container)` injecta o HTML do chat-card no container
- Listeners attached programaticamente (em vez de `onclick=...` inline)
- `submitQuery()` parser SSE inalterado (3 fases: meta -> token -> done)
- Fontes documentais agora usam `ficheiroUrl()` do `api.js` (com token)
- `loadStats()` chama `/documentos` via `apiFetch` (silencioso se falhar
  — admin tab pode estar sem Qdrant)

#### `js/admin.js` — vistas exclusivas do admin

- `renderDocumentos(container)` — upload + grid de cards + stats
- `renderAuditoria(container)` — tabela com nova coluna **"Utilizador"**
  (mostra `(anonimo)` em italico para registos legados sem auth)
- `loadAudit()` formata `timestamp` com `dd/MM HH:mm:ss` (era so HH:mm:ss)

#### `js/historico.js` — vista do farmaceutico

- `renderHistorico(container)` — tabela mais magra (sem coluna utilizador,
  obviamente; sem coluna duracao porque nao interessa)
- Detail row mostra so a resposta (a query reformulada nao interessa ao
  utilizador final)

#### `js/main.js` — router

- Ao carregar: se ha `getToken()`, tenta `obterUtilizadorAtual()` -> entra
  na app; senao mostra login
- Form submit do login -> `login()` -> `entrarNaApp()`
- `entrarNaApp()` faz o swap `loginView.hidden = true; appView.hidden = false`,
  preenche `userName` / `userRole`, monta as tabs conforme o papel,
  chama `checkHealth()`
- **Tabs por papel:**
  - admin: `Consulta` | `Documentos` | `Auditoria`
  - farmaceutico: `Consulta` | `Historico`
- `voltarParaLogin(msg?)` faz o swap inverso, limpa tabs/content, mostra
  mensagem se passada
- Listener global de `'auth:expired'` chama `voltarParaLogin` — qualquer 401
  em qualquer vista cai automaticamente no login sem ter de espalhar
  verificacoes pelos modulos
- Botao logout chama `logout()` + `voltarParaLogin()`

### 3.3 `index.html` reescrito

Estrutura nova:

```html
<body>
  <div id="login-view" class="login-view">
    <div class="login-card">
      <img class="login-logo" ...>
      <h1>RAG Farmaceutico</h1>
      <form id="loginForm" class="login-form">...</form>
    </div>
  </div>

  <div id="app-view" class="app-view" hidden>
    <header class="header">
      <div class="header-left">...</div>
      <div class="header-right">
        <div class="status-badge">...</div>
        <div class="user-chip">
          <div class="user-info">
            <span class="user-name" id="userName"></span>
            <span class="user-role" id="userRole"></span>
          </div>
          <button class="logout-btn" id="logoutBtn">Sair</button>
        </div>
      </div>
    </header>
    <nav class="tabs-bar" id="tabsBar"></nav>
    <main id="contentArea"></main>
    <div class="footer">...</div>
  </div>

  <script type="module" src="/static/js/main.js"></script>
</body>
```

A `<nav>` e o `<main>` ficam vazios no HTML — sao montados pelo `main.js`
conforme o papel.

### 3.4 `style.css` — blocos novos

Anexado no fim do ficheiro, depois do existente (~280 linhas):

- `[hidden] { display: none !important }` — ver bug fix abaixo
- `.login-view` — fullscreen flex com gradiente teal (mesma paleta do header)
- `.login-card` — branco, padding 2.5rem, shadow forte, max-width 380px
- `.login-logo`, `.login-title`, `.login-subtitle`, `.login-form`,
  `.login-field`, `.login-btn`, `.login-error`, `.login-footer`
- `.header-right` — flex para acomodar `.status-badge` + `.user-chip`
- `.user-chip` — pill com `.user-info` (nome+papel empilhados) + `.logout-btn`
- `.user-role-admin` (amarelo `#fef9c3`) e `.user-role-farmaceutico`
  (verde `#bbf7d0`) — distincao visual subtil no chip do header
- `.audit-user`, `.audit-role`, `.audit-user-anon` — formatacao da nova
  coluna "Utilizador" da auditoria
- Media query (max-width 640px): empilha o header-right e reduz padding
  do login-card

---

## Bug fix mid-session: login passava mas a vista nao trocava

A Liane testou o login e reportou "carreguei em Entrar e nao aconteceu nada".
Logs do servidor mostravam o contrario — sete sequencias
`POST /auth/login 200 -> GET /auth/me 200 -> GET /health 200`, todas bem
sucedidas. O JS estava a correr, o token estava a ser guardado e a
`entrarNaApp()` chamava `loginView.hidden = true; appView.hidden = false`.

**Causa:** especificidade CSS. O atributo HTML `hidden` traduz-se em
`[hidden] { display: none }` (regra default do browser). A nossa regra
`.login-view { display: flex }` tinha a mesma especificidade (uma classe
== um atributo) mas vinha depois — ganhava. Resultado: `loginView.hidden =
true` punha o atributo, mas o `display: flex` continuava a vencer e o ecra
de login ficava por cima da app.

**Fix:** adicionado `[hidden] { display: none !important; }` no topo do
bloco de estilos do login. Comentario no CSS explica o motivo para nao se
voltar a remover sem perceber.

Lição util: o atributo `hidden` so e seguro se nenhum estilo posterior
puser `display` na mesma especificidade. Em projectos com utility classes
isto morde.

---

## Decisoes arquitecturais desta sessao

### Token para `/ficheiros` — query param em vez de cookies/signed URLs

`<a href="/ficheiros/...">` aberto em nova tab nao envia cookies de outra
origem nem o header `Authorization`. Tres opcoes consideradas:

| Abordagem | Pro | Contra |
|---|---|---|
| Cookies HttpOnly | nativo do browser | refactor grande da auth toda |
| Signed URLs curtos | seguro, scope-restrito | endpoint extra `/ficheiros/url`, mais codigo |
| **Token na query (escolhida)** | reutiliza o JWT existente, zero refactor | token aparece no historico do browser |

Aceitavel porque (a) os tokens expiram em 8h, (b) os PDFs sao a documentacao
de referencia (publicada — bula, monografia), nao dados sensiveis. **Risco
real e baixo** mas vale uma nota no relatorio na seccao de seguranca.

### Token storage — `localStorage`

Standard para SPAs. Vulneravel a XSS, mas a app nao tem inputs ricos que
permitam injeccao (so um `<input type="text">` cujo conteudo nunca e
renderizado como HTML). Suficiente para a demo academica.

### Modulos ES sem bundler

`<script type="module">` + `import` nativo. Sem npm, sem webpack, sem
`package.json`. Funciona em todos os browsers modernos. Manteve a filosofia
"backend Python, frontend simples" que o projeto teve desde o inicio.

---

## Comportamento final

| Cenario | Comportamento |
|---|---|
| Abrir `/` sem token | Mostra ecra de login (gradiente teal, card branco) |
| Login com `admin` / `admin2026` | Tres abas: Consulta, Documentos, Auditoria |
| Login com `farmaceutico` / `farmaceutico2026` | Duas abas: Consulta, Historico |
| Pedido a endpoint protegido sem token | 401, ja **nao** acontece via UI (gateada) |
| Token expirar a meio (8h depois) | Proximo pedido devolve 401 -> `auth:expired` -> volta ao login com mensagem |
| Logout | Limpa `localStorage`, reset de tabs/content, volta ao login |
| Refresh da pagina (com token valido) | Re-entra na app directamente, sem re-login |
| Fonte clicada no chat | Abre o PDF em nova tab via `/ficheiros/.../doc.pdf?token=...#page=N` |
| Farmaceutico tenta fazer upload | Nao tem a aba; backend devolveria 403 se chamasse directo |
| Auditoria (admin) | Nova coluna "Utilizador" — registos legados aparecem como `(anonimo)` em italico |
| Historico (farmaceutico) | So as proprias consultas (filtrado no backend por `username`) |

---

## Validacoes feitas

- Login via curl (`admin` / `admin2026`) -> 200, token valido emitido
- `GET /auth/me` com o token -> `{"username":"admin","papel":"admin"}`
- `GET /documentos` **sem** token -> 401 Unauthorized (conforme esperado)
- Imports do backend: `requer_admin`, `utilizador_atual_query` resolvem OK
- `bcrypt` e `pyjwt` instalados no venv local
- Server arranca sem erros (uvicorn + lifespan + `inicializar_bd()`)
- Frontend: 6 ficheiros JS servidos com 200 OK (logs)
- Bug fix do `[hidden]` confirmado a olho apos refresh forcado

**Nao corridos nesta sessao:**
- Teste manual do chat / fontes clicaveis com o Qdrant a correr
- Teste manual do upload (admin) e do gating 403 ao farmaceutico
- Teste manual de expiracao real do token (precisa esperar 8h ou mexer no `.env`)
- Suite de testes (Fase 4 do plano — `tests/test_auth.py` ainda nao existe)

---

## Ficheiros modificados (uncommitted no fim da sessao)

### Pre-existente (Fase 1+2, ja estava no disco quando a sessao comecou)

```
M  .gitignore                                <- + data/auth.db
M  requirements.txt                          <- + bcrypt, pyjwt
M  src/api/audit.py                          <- migracao JSONL -> SQLite, + utilizador/papel
M  src/config.py                             <- + JWT_*, AUTH_DB_PATH, SEED_*
?? src/auth/__init__.py                      <- package novo
?? src/auth/modelos.py
?? src/auth/db.py
?? src/auth/seguranca.py
?? src/auth/dependencias.py                  <- (modificado tambem nesta sessao)
?? src/auth/seed.py
?? docs/plano_login_perfis.md                <- documento de trabalho
```

### Fase 3 (esta sessao)

```
M  src/auth/dependencias.py                  <- + utilizador_atual_query
M  src/api/main.py                           <- gating completo + utilizador/papel no audit
M  src/api/static/index.html                 <- shell duplo (login + app)
M  src/api/static/style.css                  <- + login + user-chip + [hidden] fix
D  src/api/static/app.js                     <- substituido pela pasta js/
?? src/api/static/js/api.js
?? src/api/static/js/auth.js
?? src/api/static/js/chat.js
?? src/api/static/js/admin.js
?? src/api/static/js/historico.js
?? src/api/static/js/main.js
```

### Outros artefactos (nao relacionados com a sessao)

```
?? data/audit/audit_2026-05-19.jsonl         <- runtime, devia ir para .gitignore
?? data/audit/audit_2026-05-20.jsonl
?? data/audit/audit_2026-05-22.jsonl
?? docs/CONTEXTS/                            <- CONTEXT1..7 movidos para aqui
D  docs/CONTEXT1.md                          <- (idem)
D  docs/CONTEXT2.md
... [CONTEXT3..7]
```

Total: **~15 ficheiros tocados + 7 novos** (sem contar artefactos JSONL).

---

## Pontos abertos / proximos passos

### Curto prazo (proxima sessao)

1. **Commit das mudancas.** Sugestao de 4 commits tematicos:
   - `feat(auth): backend completo (JWT + bcrypt + SQLite + endpoints login/me/historico)` — Fase 1+2 inteira
   - `feat(auth): proteger endpoints existentes + propagar utilizador para o audit` — backend Fase 3
   - `refactor(frontend): modulos ES + ecra de login + vistas por papel` — frontend Fase 3
   - `fix(css): atributo [hidden] precisa de !important para vencer display:flex`
2. **Adicionar `data/audit/*.jsonl` ao `.gitignore`** — sao artefactos da
   sessao da Fase 1+2 antes da migracao para SQLite; nao deviam estar aqui
3. **Mover os CONTEXTs** — a `docs/CONTEXTS/` ja existe; eliminar
   definitivamente os ficheiros antigos `docs/CONTEXT[1-7].md` (estao
   marked-as-deleted mas nao committed)

### Medio prazo (Fase 4 do plano)

4. **`tests/test_auth.py`** — cenarios minimos:
   - `gerar_hash_password` + `verificar_password` (positivo e negativo)
   - `criar_token` + `descodificar_token` (valido, expirado, mal formado)
   - `POST /auth/login` (200 com creds validas, 401 sem)
   - Gating: 401 sem token, 403 farmaceutico em rota de admin
   - `utilizador_atual_query` aceita `?token=...`
5. **Actualizar `README.md`** — adicionar fluxo de seed (`python -m src.auth.seed`),
   credenciais de demo, fluxo de login
6. **Back-documentar RF15 no relatorio** — origem (estagio), permissoes,
   stack tecnica, decisoes de seguranca. **Acao academica obrigatoria.**

### Pontos academicos / nao-codigo

7. **Avisar orientadores UTAD** (Paulo Oliveira, Eduardo Pires) da inclusao
   da RF15 — referido na sec. 1 do [plano](docs/plano_login_perfis.md)
8. **Diagrama de casos de uso** — adicionar os dois actores (farmaceutico,
   admin) e os respectivos casos
9. **Capitulo de governanca** — referir RBAC + auditoria por utilizador
   como reforco do EU AI Act / RF14

### Herdados de CONTEXTs anteriores (ainda por fazer)

- Mensagens de erro em portugues (Pydantic vem em ingles)
- Persistir a conversa no `localStorage` para sobreviver a refresh
- `GET /conversas/{session_id}` para agrupar audit logs por sessao
- Decisao do LangChain (opcao A vs B do CONTEXT7)
- README ainda diz "Claude 3.5 Sonnet"
- Limpeza dos 2.27GB do bge-reranker + ~1GB sentence_transformers no venv

---

## Resumo executivo

- **Fase 3 do plano de login concluida.** App inteira gateada por JWT.
  Tres endpoints de admin (`/upload`, `/ingestao`, `/audit`); quatro de
  qualquer utilizador autenticado (`/consulta`, `/consulta/stream`,
  `/documentos`, `/historico`, `/ficheiros`).
- **Frontend reescrito em modulos ES.** O `app.js` monolitico desapareceu;
  6 modulos pequenos na pasta `js/` substituem-no.
- **Ecra de login + duas vistas por papel** funcionais. Token em
  `localStorage`, 8h de validade, logout explicito, expiracao trata-se
  via evento global `auth:expired`.
- **`/ficheiros/{tipo}/{nome}` agora aceita `?token=`** — necessario porque
  `<a href>` nao envia headers. Risco aceitavel.
- **Auditoria ganha coluna "Utilizador"** na vista do admin; registos
  legados aparecem como `(anonimo)`.
- **1 bug fix nao trivial:** atributo HTML `hidden` precisa de
  `[hidden] { display: none !important }` quando alguma classe que vai
  ser escondida tem `display` explicito.
- **Nao quebrou nada do que ja funcionava:** chat com streaming, fontes
  clicaveis, reformulator e CRAG continuam a correr exactamente como
  no fim do CONTEXT7. Tudo o que mudou foi acrescentado por cima.
- **Fase 4 (testes + documentacao + relatorio) continua em aberto.**
  E a unica peca obrigatoria que falta para fechar a RF15.
