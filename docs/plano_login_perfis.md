# Plano de Implementação — Autenticação e Perfis de Utilizador

> Documento de trabalho. Criado a 2026-05-22.

## 1. Contexto e origem

Funcionalidade pedida pelo **orientador de estágio (Ricardo Costa, Teclab)**.
**Não consta da proposta formal de projeto.**

**Ação académica obrigatória:** back-documentar no relatório como requisito funcional
novo — sugestão **RF15 — Autenticação e perfis de utilizador** — identificando que a
origem é o contexto de estágio. Avisar os orientadores UTAD (Paulo Oliveira, Eduardo
Pires). Requisitos evoluírem durante um estágio é normal; o que se evita é ter código
sem requisito associado, porque é o tipo de coisa que um júri questiona na defesa.

Nota positiva: RBAC + auditoria por utilizador **reforça** o capítulo de governança /
EU AI Act que o projeto já aborda (RF14, transparência).

## 2. Decisões tomadas

| # | Tema | Escolha |
|---|---|---|
| 1 | Permissões do papel **farmacêutico** | Chat (consulta) + ver documentos |
| 2 | Permissões do papel **admin** | Acesso total |
| 3 | Criação de contas | Pré-criadas por *seed script* |
| 4 | Interface | Vistas separadas por papel |
| 5 | Frontend | Reorganizado em módulos ES (vanilla, sem *build step*) |
| 6 | Base de dados | SQLite agora; migração para PostgreSQL como tarefa isolada futura (fora do caminho crítico) |
| 7 | Registo de auditoria | Migra de ficheiros JSONL para uma tabela SQLite `consultas` |
| 8 | Histórico por utilizador | Nova funcionalidade — o utilizador vê as suas consultas anteriores |

## 3. Matriz de permissões

| Endpoint | Público | Farmacêutico | Admin |
|---|:---:|:---:|:---:|
| `/`, `/static/*` (login + app) | ✅ | ✅ | ✅ |
| `GET /health` | ✅ | ✅ | ✅ |
| `POST /auth/login` | ✅ | ✅ | ✅ |
| `GET /auth/me` | — | ✅ | ✅ |
| `POST /consulta` | — | ✅ | ✅ |
| `POST /consulta/stream` | — | ✅ | ✅ |
| `GET /documentos` | — | ✅ | ✅ |
| `GET /ficheiros/{tipo}/{nome}` | — | ✅ | ✅ |
| `POST /upload` | — | ❌ | ✅ |
| `POST /ingestao` | — | ❌ | ✅ |
| `GET /audit` | — | ❌ | ✅ |

## 4. Stack técnica

- **Autenticação:** OAuth2 *password flow* + **JWT** (HS256) — encaixa no backend
  *stateless* já existente
- **Armazenamento de utilizadores:** **SQLite** (`data/auth.db`) — o projeto ainda
  não tem base de dados relacional
- **Hashing de passwords:** `bcrypt` — passwords nunca guardadas em claro
- **JWT:** `PyJWT`
- `python-multipart` — **já está** no `requirements.txt` (necessário para o
  formulário OAuth2)

Dependências a acrescentar ao `requirements.txt`:

```
bcrypt
pyjwt
```

## 5. Arquitetura — Backend

### 5.1 Novo package `src/auth/`

| Ficheiro | Responsabilidade |
|---|---|
| `modelos.py` | Modelos Pydantic: `Utilizador`, `Token`, `TokenData` |
| `db.py` | Ligação SQLite; `inicializar_bd()`, `obter_utilizador()`, `criar_utilizador()` |
| `seguranca.py` | `hash_password()`, `verificar_password()`, `criar_token()`, `descodificar_token()` |
| `dependencias.py` | Dependencies FastAPI: `utilizador_atual()` (→ 401), `requer_admin()` (→ 403) |
| `seed.py` | Script `python -m src.auth.seed` — cria a tabela e as contas iniciais |

### 5.2 Tabela SQLite

```sql
CREATE TABLE IF NOT EXISTS utilizadores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    papel         TEXT NOT NULL CHECK (papel IN ('farmaceutico', 'admin')),
    criado_em     TEXT NOT NULL
);
```

### 5.3 Endpoints novos

- `POST /auth/login` — recebe `username` + `password` (formulário OAuth2 via
  `OAuth2PasswordRequestForm`), verifica contra a BD, devolve
  `{access_token, token_type: "bearer"}`. Devolve 401 se as credenciais forem inválidas.
- `GET /auth/me` — devolve `{username, papel}` do utilizador autenticado. Usado pelo
  frontend para decidir que vista mostrar.

### 5.4 Proteção dos endpoints existentes

Aplicar as dependencies conforme a matriz da secção 3:
- `utilizador_atual` → consulta, consulta/stream, documentos, ficheiros
- `requer_admin` → upload, ingestao, audit
- `/health` e a página inicial ficam **públicas** (a página de login tem de ser
  acessível sem token)

### 5.5 Auditoria

`registar_consulta()` ganha os campos `utilizador` e `papel`. O registo JSONL já tem
`session_id`; com o utilizador, o trilho de auditoria fica completo.

### 5.6 Configuração

- `.env` ganha: `JWT_SECRET_KEY`, `SEED_ADMIN_PASSWORD`, `SEED_FARMACEUTICO_PASSWORD`
  (o `.env` não vai para o repositório, por isso as passwords seed não são commitadas)
- `src/config.py` lê `JWT_SECRET_KEY`, `JWT_ALGORITHM` (`"HS256"`),
  `JWT_EXPIRA_MINUTOS`
- Acrescentar `data/auth.db` ao `.gitignore`

## 6. Arquitetura — Frontend

### 6.1 Nova estrutura de `src/api/static/`

```
src/api/static/
├── index.html          # shell: #login-view + #app-view
├── js/
│   ├── api.js           # fetch + header Authorization + tratamento de 401
│   ├── auth.js          # login(), logout(), token em localStorage, papel
│   ├── chat.js          # vista do farmacêutico (chat SSE, bubbles, fontes)
│   ├── admin.js         # vista do admin (chat + upload + documentos + auditoria)
│   └── main.js          # entrada: sem token → login; com token → vista por papel
├── css/
│   ├── style.css        # base partilhada (tokens, layout)
│   ├── chat.css
│   └── admin.css
└── assets/              # favicon.ico, logo.png
```

Módulos ES (`<script type="module">`, `import`/`export`) — sem npm, sem bundler.
Cada feature futura entra como módulo novo sem mexer nos restantes.

### 6.2 Fluxo de login

1. A página carrega → `main.js` procura um token no `localStorage`
2. Sem token (ou expirado) → mostra `#login-view`
3. Submeter o login → `api.js` faz `POST /auth/login` → recebe o JWT → `auth.js` guarda-o
4. `GET /auth/me` → obtém `{username, papel}`
5. Esconde o login, mostra a app; `main.js` rende `chat.js` (farmacêutico) ou
   `admin.js` (admin)
6. Cada chamada de `api.js` anexa `Authorization: Bearer <token>`; perante um 401,
   limpa o token e volta ao login
7. Botão de logout → limpa o token → volta ao login

## 7. Passos de implementação

### Fase 1 — Fundação de autenticação (backend) ✅ concluída
- [x] Acrescentar `bcrypt` e `pyjwt` ao `requirements.txt` e instalar
- [x] Acrescentar `JWT_SECRET_KEY` e as passwords seed ao `.env`; lê-las em `config.py`
- [x] Acrescentar `data/auth.db` ao `.gitignore`
- [x] Criar o package `src/auth/` com `modelos.py`, `db.py`, `seguranca.py`
- [x] Criar a tabela `utilizadores` (SQLite)
- [x] `src/auth/seed.py` — criar as contas iniciais (admin + farmaceutico)
- [x] Correr o seed e confirmar as contas na base de dados

### Fase 2 — Login, auditoria em BD e histórico (backend) ✅ concluída
- [x] `POST /auth/login` (devolve o JWT) e `GET /auth/me`
- [x] `src/auth/dependencias.py` — `utilizador_atual()` e `requer_admin()`
- [x] Tabela `consultas` no SQLite + funções de acesso no `db.py`
- [x] Migrar a auditoria de JSONL para a tabela `consultas` (`audit.py`), com `utilizador` e `papel`
- [x] Reescrever `GET /audit` para ler da tabela `consultas`
- [x] Endpoint `GET /historico` — consultas do utilizador autenticado

> Nota: a proteção dos endpoints existentes passou para a Fase 3, para ser feita
> em conjunto com o frontend — assim a app nunca fica num estado partido (endpoints
> a exigir token antes de o frontend o saber enviar).

### Fase 3 — Frontend e proteção de acesso
- [ ] Reestruturar `src/api/static/` (criar `js/`, `css/`, `assets/`)
- [ ] `api.js` — wrappers de fetch com o header `Authorization`; em 401, voltar ao login
- [ ] `auth.js` — login / logout, token no `localStorage`
- [ ] Ecrã de login no `index.html`
- [ ] Migrar o chat atual de `app.js` para `chat.js`
- [ ] `admin.js` — vista do admin (chat + upload + documentos + auditoria)
- [ ] Secção de histórico na vista do utilizador (lê `GET /historico`)
- [ ] `main.js` — encaminhar para a vista conforme o papel
- [ ] Botão de logout
- [ ] Proteger os endpoints — autenticado: consulta, consulta/stream, documentos, ficheiros, historico; só admin: upload, ingestao, audit. Feito aqui (com o frontend) para a app nunca ficar partida
- [ ] Confirmar que `/health`, `/auth/login` e a página de login ficam públicos

### Fase 4 — Testes e documentação
- [ ] `tests/test_auth.py` — hash/verificação, token (válido / expirado / inválido),
      `/auth/login`, gating (401 sem token, 403 farmacêutico numa rota de admin)
- [ ] Atualizar `README.md` e `docs/notas.md` (contas seed, fluxo de login)
- [ ] **Back-documentar no relatório:** RF15, com origem no estágio
- [ ] Registar a sessão no próximo `CONTEXT`

## 8. Segurança — âmbito

**Dentro de âmbito:** passwords com hash `bcrypt`, JWT com expiração, segredo fora do
repositório (`.env`), controlo de acesso por papel.

**Fora de âmbito (trabalho futuro — mencionar no relatório):** MFA, *refresh tokens*,
recuperação de password, OAuth externo, *rate limiting*, HTTPS (necessário em produção;
na demo local corre em HTTP).

## 9. Pontos em aberto

- **Duração do token** — sugestão: 8h (480 min), equivalente a um turno de trabalho
- **Vista do admin** — embutir o chat ou ter navegação para ele? Recomendação: o admin
  vê o chat + as secções de gestão na mesma vista, com navegação interna
- **`index.html`** — manter um único ficheiro (login + app alternados por JS) é mais
  simples sem *build*; recomendado

## 10. Para o relatório

- Acrescentar **RF15** à secção de requisitos, marcando a origem (estágio / Teclab)
- Atualizar diagramas (casos de uso / arquitetura) com os dois atores: farmacêutico e admin
- Referir RBAC + auditoria por utilizador no capítulo de governança / conformidade
  (liga ao EU AI Act e ao RF14)
- Documentar como trabalho futuro o que ficou fora de âmbito (secção 8)
