# CONTEXT7.md — Chat conversacional com reformulacao contextual (history-aware retriever)

## Snapshot no fim do CONTEXT6

- Pipeline RAG ponta-a-ponta a funcionar; commit `017518a tentar diminuir latencia` no `main`
- Latencia: ~35.5s em queries longas, ~22-26s em curtas (RNF01 de <=10s ainda nao cumprido)
- Stack LLM: Claude Sonnet 4.6 em toda a stack de query/guardrails, Gemini so para embeddings
- Cliente Anthropic singleton, skip-CRAG heuristico, reranker com `temperature=0`
- API com 6 endpoints (`/consulta`, `/ingestao`, `/upload`, `/documentos`, `/health`, `/audit`)
- Frontend: 1 pergunta -> 1 resposta. Sem historico, sem chat, sem follow-ups
- 1 PDF indexado (`brufen_folheto.pdf`)

A Liane abriu a sessao a pedir feedback geral sobre o estado e depois sugeriu transformar a interaccao em **chat conversacional** ("neste momento faz-se uma pergunta e tem-se resposta e depois nao acontece nada").

---

## Decisao de arquitectura: history-aware retriever

Duas opcoes discutidas:

| Abordagem | Latencia extra por follow-up | Qualidade do retrieval |
|---|---|---|
| **Reformulacao contextual** (escolhida) | +1 chamada Sonnet (~1-2s) | Retriever sempre recebe query autonoma |
| **Passar historico ao generator** | 0 (so mais tokens) | Retriever fica "cego" ao contexto da conversa |

A reformulacao contextual venceu por tres razoes:
1. Sem ela, follow-ups como "e a posologia?" mandam ao retriever o termo isolado "posologia" -> chunks irrelevantes
2. +1-2s e <5% da latencia total (~30s); so paga em mensagens de seguimento, nao na 1a
3. Padrao de papers/LangChain ("history-aware retriever") — defende-se sozinho no Cap. 4.3.3 do relatorio

Backend mantem-se **stateless**: o cliente envia o historico completo em cada pedido. Isto evita gestao de sessoes server-side e segue a filosofia REST.

---

## Backend (6 ficheiros)

### `src/api/models.py`

Novo schema `Mensagem`:
```python
class Mensagem(BaseModel):
    role: Literal["user", "assistant"]
    conteudo: str
```

`ConsultaRequest` ganha dois campos novos:
- `historia: list[Mensagem]` (default `[]`)
- `session_id: str | None` (default `None`, gerado pelo frontend)

### `src/query/prompt.py`

Novo template `PROMPT_REFORMULACAO_CONTEXTUAL`. Instrui o LLM a:
1. Devolver a pergunta EXACTAMENTE como esta se ja for autonoma
2. Reescrever se usar referencias implicitas ("e a posologia?", "e isso?", "e nos idosos?"), incluindo o medicamento/tema discutido
3. Preservar intencao, sem adicionar informacao nao pedida
4. Manter concisao

### `src/query/reformulator.py` (NOVO)

Modulo de 60 linhas com `reformular_com_historia(query, historia) -> str`:
- **Early return se `historia` vazia** — 1a pergunta da conversa NAO paga a chamada LLM extra
- Aceita tanto objectos `Mensagem` (Pydantic) como dicts `{role, conteudo}` (via `hasattr`)
- Usa `obter_cliente()` singleton, `temperature=0`, `max_tokens=300`
- Defesa contra outputs anormais (vazio ou >2000 chars): cai para a query original

### `src/query/pipeline.py`

`consultar()` ganha parametro `historia: list | None = None`.

Nova **etapa 1b** entre input_guard e retriever:
```
input_guard -> [reformular_com_historia se historia] -> retriever -> reranker -> CRAG -> generator -> output_guard
```

A variavel `query_para_retrieval` propaga-se daqui em diante: retriever, reranker, CRAG e generator recebem sempre a query autonoma, nao a original. O CRAG pode ainda reformular por cima (questao de qualidade), pelo que `query_usada` na resposta reflecte a cadeia inteira (contextual + CRAG).

### `src/api/audit.py`

`registar_consulta()` aceita parametro extra `session_id: str | None = None`. Campo `session_id` adicionado ao registo JSONL, logo a seguir ao `id`. Permite reconstruir conversas a partir dos logs (ex: `jq 'select(.session_id == "xxx")' audit_*.jsonl`).

### `src/api/main.py`

Endpoint `/consulta` passa `historia=pedido.historia` para `consultar()` e `session_id=pedido.session_id` para `registar_consulta()` via BackgroundTasks. Nenhum outro endpoint mexido.

---

## Frontend (3 ficheiros)

### `src/api/static/index.html`

Tab "Consulta" rescrito. Estrutura antiga (search-card + response-card) substituida por:

```
.chat-card
├── .chat-header (titulo "CONVERSA" + botao "+ Nova conversa")
├── .chat-thread (#chatThread, scroll, max-height 60vh)
│   └── .chat-empty (mensagem de placeholder ate haver mensagens)
├── .error-card (movido para dentro do chat-card)
└── .chat-input-area
    ├── .filters-row (filtro de tipo)
    └── .search-row (input + botao "Enviar")
```

Tabs "Documentos" e "Auditoria" intactos.

### `src/api/static/app.js`

Estado novo no topo:
```js
let mensagens = [];   // [{role: 'user'|'assistant', conteudo: '...'}]
let sessionId = null; // UUID gerado por crypto.randomUUID()
```

`DOMContentLoaded` gera `sessionId` ao carregar a pagina.

`submitQuery()` reescrito:
1. Append da bubble do utilizador (`appendUserBubble` devolve ID para conseguir remover depois)
2. Push `{role:'user', conteudo:query}` ao `mensagens`
3. Append da bubble "a pensar..." (animacao de 3 pontos)
4. `fetch /consulta` com `{query, tipo_documento, historia: mensagens.slice(0,-1), session_id}`
   — envia historico ANTERIOR a esta mensagem (a actual vai no campo `query`)
5. Em caso de sucesso: remove thinking bubble, append da resposta, push ao `mensagens`
6. Em caso de erro: remove thinking bubble + user bubble, `mensagens.pop()`, restaura texto no input

`novaConversa()`:
- Reset `mensagens = []`
- Novo `sessionId`
- Limpa o thread, restaura a empty message, foca o input

Renderizadores:
- `appendUserBubble(texto)` — bubble teal a direita, devolve ID
- `appendThinkingBubble()` — bubble com 3 dots animados + "A consultar a documentacao..."
- `appendAssistantBubble(data, queryOriginal)` — bubble branca a esquerda com:
  - Linha discreta "Interpretado como: <query reformulada>" se diferir da original (transparencia, RF14/EU AI Act)
  - Resposta formatada (reutiliza `formatResponse` existente)
  - Meta-row: chunks usados + badge de contexto suficiente/limitado
  - Fontes documentais como tags

### `src/api/static/style.css`

Bloco novo de ~280 linhas anexado no fim, antes da media query mobile (que tambem ganhou regras para `.chat-thread` e `.chat-bubble`).

Tokens reaproveitados (`--primary`, `--bg-card`, `--border`, etc.) — visualmente consistente com o resto da app.

Highlights:
- `.chat-bubble-user`: gradiente teal (mesmo do header), border-radius assimetrico (canto inferior direito menor)
- `.chat-bubble-assistant`: branco com borda, canto inferior esquerdo menor
- `.thinking-dots`: 3 pontos com `@keyframes thinking-bounce` (delays escalonados)
- `.chat-reformulada`: separador tracejado discreto a cima da resposta quando ha reformulacao
- `.chat-input-area`: filtro + input num footer agarrado ao card, separado por borda

---

## Bug fix mid-session: `[object Object]` no error card

A Liane testou com a query "ola" (3 chars). O `min_length=5` do Pydantic devolveu um 422 com `detail` como **array de objectos** (formato padrao do FastAPI para erros de validacao):

```json
{"detail": [{"loc": ["body", "query"], "msg": "String should have at least 5 characters", "type": "string_too_short", ...}]}
```

O JS antigo fazia `new Error(err.detail || 'Erro')` — convertia o array via `toString()` -> `"[object Object]"`.

**Fix em `app.js`:** nova funcao `formatErrorDetail(detail)` que trata:
- `string` -> passa directo (HTTPException nossa)
- `Array` -> formata cada item como `"campo: msg"` e junta com `;`
- `object` solto -> tenta `detail.msg`, senao `JSON.stringify`

Aplicada tanto em `submitQuery` como em `uploadDocument` (mesmo padrao).

**UX bonus do mesmo fix:** em caso de erro, agora removemos tambem a user bubble do DOM (alem da thinking) e **restauramos o texto no input** — o utilizador nao tem de reescrever para corrigir. Necessario porque a bubble do utilizador ja tinha sido appended antes de receber a resposta.

`appendUserBubble()` passou a devolver o ID do elemento (igual ao `appendThinkingBubble()`).

---

## Comportamento final

| Cenario | Latencia | Comportamento |
|---|---|---|
| 1a pergunta da conversa (`historia=[]`) | igual ao anterior (~30s) | Reformulator faz early return, zero overhead |
| Pergunta de seguimento ("e a posologia?") | +1-2s | Reformulator reescreve para "qual a posologia do brufen?" antes do retriever |
| Pergunta autonoma de seguimento | +1-2s | Reformulator devolve a query inalterada (mas paga a chamada LLM) |
| Erro de validacao Pydantic | n/a | Mensagem legivel ("query: String should have at least 5 characters"), input restaurado |
| Erro 500 da API | n/a | `detail` (string) mostrado directamente |
| Botao "+ Nova conversa" | instantaneo | Reset de `mensagens`, novo `sessionId`, thread limpo |

---

## Auditoria: agrupar conversas por sessao

Cada registo JSONL ganha o campo `session_id`. Para reconstruir uma conversa inteira a partir dos logs:

```bash
jq -s 'sort_by(.timestamp) | map(select(.session_id == "abc-123"))' data/audit/audit_2026-05-18.jsonl
```

O endpoint `GET /audit` actual nao agrupa por sessao — devolve registos pelados. Endpoint `GET /conversas/{session_id}` ficou no plano original mas nao foi implementado nesta sessao (decidido como "fica para depois" no inicio).

---

## Validacoes feitas

- `python -c "from src.query.pipeline import consultar; from src.query.reformulator import reformular_com_historia; from src.api.models import ConsultaRequest, Mensagem; from src.api.audit import registar_consulta; print('OK')"` -> OK
- Schema `ConsultaRequest` aceita payload com `historia` (lista de dicts) e `session_id` -> validado
- Teste manual no browser: 1 mensagem "ola" expos o bug `[object Object]`, corrigido em seguida

**Nao corridos nesta sessao:**
- Suite de testes (`tests/test_pipeline.py` precisaria de cenarios multi-turn novos)
- Teste real end-to-end de uma conversa de 3+ turnos com o Qdrant a correr
- `tests/test_reformulator.py` (estava no plano, ficou para a proxima sessao)

---

## Ficheiros modificados (nao-comitados no fim da sessao)

```
M  docs/CONTEXT7.md (este ficheiro)         <- novo
M  src/api/audit.py                         <- + session_id
M  src/api/main.py                          <- passa historia e session_id ao pipeline
M  src/api/models.py                        <- + Mensagem, ConsultaRequest.historia, session_id
M  src/api/static/app.js                    <- estado de conversa, bubbles, formatErrorDetail
M  src/api/static/index.html                <- chat-card no tab consulta
M  src/api/static/style.css                 <- ~280 linhas de chat styles
M  src/query/pipeline.py                    <- etapa 1b: reformulacao contextual
M  src/query/prompt.py                      <- + PROMPT_REFORMULACAO_CONTEXTUAL
?? src/query/reformulator.py                <- novo modulo
```

---

## Pontos abertos / proximos passos

1. **Testar a conversa real ponta-a-ponta** — apos `docker compose down && docker compose up --build`, fazer:
   - "O que e o brufen?" (1a pergunta, sem reformulacao)
   - "e a posologia?" (deve aparecer linha "Interpretado como: qual a posologia do brufen?")
   - "e nos idosos?" (3o turno, contexto cumulativo)
2. **Testes unitarios do reformulator** (`tests/test_reformulator.py`) — adiados na sessao:
   - Caso historico vazio (early return)
   - Caso follow-up vago (reformula)
   - Caso pergunta autonoma (devolve igual)
   - Mock do `obter_cliente()` para nao consumir tokens
3. **Mensagens de erro em portugues** — actualmente as validacoes do Pydantic vem em ingles ("String should have at least 5 characters"). Opcoes: validators customizados nos schemas com mensagens PT, ou mapping no `formatErrorDetail()` para os `type` mais comuns
4. **localStorage no frontend** — actualmente a conversa morre num refresh. Decisao adiada na fase de planeamento; se for util para a demo, valia a pena guardar `mensagens` e `sessionId` no localStorage
5. **`GET /conversas/{session_id}`** — agrupar audit logs por sessao para o tab Auditoria conseguir mostrar threads em vez de mensagens soltas
6. **Commit das mudancas desta sessao** — 9 ficheiros modificados + `reformulator.py` novo + `CONTEXT7.md`. Sugestao de 3 commits tematicos:
   - feat(chat): backend stateless com reformulacao contextual de queries (models, prompt, reformulator, pipeline, audit, main)
   - feat(chat): frontend com thread de mensagens, bubbles e historico no cliente (index.html, app.js, style.css)
   - fix(ui): mostrar erros de validacao Pydantic em vez de "[object Object]"
7. **README desactualizado** (heranca de sessoes anteriores) — ainda diz "Claude 3.5 Sonnet"; sem relacao directa com esta sessao mas continua pendente

### Memorias actualizadas

Nenhuma actualizacao a `memory/MEMORY.md`. A estrategia LLM (`project_crag_llm_strategy.md`) continua valida: o reformulator e mais uma chamada Claude Sonnet 4.6, alinhado com o resto da stack. Vale a pena considerar adicionar uma memoria a documentar a passagem para chat conversacional caso isto fique como padrao do sistema.

### Resumo executivo da sessao

- **Pivot arquitectural:** sistema deixou de ser Q&A pontual e passou a chat conversacional, mantendo o backend stateless
- **1 modulo novo:** `src/query/reformulator.py` (history-aware retriever)
- **9 ficheiros alterados** distribuidos por schemas, pipeline, audit, API, prompt, frontend completo
- **1 bug encontrado e corrigido durante o teste** (`[object Object]` por mau handling de erros 422)
- **Trade-off assumido:** +1-2s de latencia em follow-ups em troca de retrieval contextualmente correcto
- **Nao quebrou** comportamento existente — 1a pergunta de qualquer conversa corre exactamente como antes (early return no reformulator)
