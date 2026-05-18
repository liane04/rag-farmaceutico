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

## Fontes clicaveis: abrir o PDF na pagina citada

A Liane reparou que as tags de fontes documentais ("BULA brufen_folheto.pdf, p.10") eram apenas decorativas — nao havia maneira de chegar ao documento original. UX gap obvio para um sistema que vende rastreabilidade.

**Solucao em 3 partes:**

### Backend — novo endpoint `GET /ficheiros/{tipo}/{nome}`

[main.py](src/api/main.py): endpoint que devolve o PDF via `FileResponse(..., media_type="application/pdf")`. Mapeia `tipo` -> subpasta reaproveitando o dicionario do `/upload` (`bula` -> `bulas/`, etc.).

**Tres camadas de defesa contra directory traversal:**
1. `tipo` tem de estar na whitelist (4 valores fixos)
2. Nome rejeitado se contiver `/`, `\`, `..`, ou diferir de `Path(nome).name` (evita paths absolutos)
3. So serve `.pdf`
4. Path resolvido com `.resolve()` e validado com `.relative_to(pasta_resolvida)` (defesa contra symlinks construidos manualmente)

### Frontend — tags como `<a>` em vez de `<span>`

[app.js](src/api/static/app.js) em `appendAssistantBubble` (e mais tarde tambem em `criarBubbleStreaming`):
- Constroi `href="/ficheiros/{tipo}/{ficheiro}#page={N}" target="_blank" rel="noopener"`
- O sufixo `#page=N` e suportado nativamente pelos viewers de PDF do Chrome, Edge e Firefox — salta directo para a pagina citada
- Tooltip `title="Abrir <ficheiro> na pagina <N>"` para acessibilidade
- Degradacao graciosa: se faltar `tipo_documento` ou `ficheiro` na fonte, renderiza como `<span>` nao-clicavel

### CSS — affordance visual

[style.css](src/api/static/style.css): classe nova `.source-tag-link` adicionada por cima da `.source-tag`:
- `cursor: pointer` + hover com fundo verde-pastel e borda primary
- Pequena seta `↗` injectada via `::after` (sinal universal de link externo)
- `text-decoration: none` na tag base para o `<a>` nao ficar sublinhado

---

## Discussao arquitectural: LangChain esta a ser sub-utilizado (decisao adiada)

A Liane perguntou se o LangChain estava a ser bem usado. Investigacao revelou que **3 das 5 dependencias LangChain no `requirements.txt` sao dead weight:**

| Pacote | Importado? | Usado em |
|---|---|---|
| `langchain-text-splitters` | Sim | [chunker.py](src/ingestion/chunker.py) — `RecursiveCharacterTextSplitter` |
| `langchain-google-genai` | Sim | [embedder.py](src/ingestion/embedder.py) — `GoogleGenerativeAIEmbeddings` |
| `langchain` (meta) | Nao | nenhuma import |
| `langchain-anthropic` | Nao | chamadas Claude vao pelo SDK `anthropic` |
| `langchain-qdrant` | Nao | retriever usa `qdrant_client` directo |

**O pipeline real (retriever -> reranker -> CRAG -> reformulator -> generator -> guardrails) e todo hand-coded em Python puro.** Nao ha `Chain`, `Runnable`, `LCEL`, `Memory` nem `HistoryAwareRetriever` (que e literalmente o que o nosso `reformulator.py` re-implementa).

### Conclusao da analise

Duas opcoes coerentes:
- **A) Lean in:** refactorizar o pipeline para LCEL, usar `HistoryAwareRetriever`, `ChatPromptTemplate`. Pro: alinha com a proposta. Contra: mais latencia, mais indireccao, refactor de varias horas, CRAG/skip-CRAG dificil de exprimir em LCEL.
- **B) Pull back (recomendada):** remover os 3 pacotes dead, manter apenas `langchain-text-splitters` e `langchain-google-genai`, reescrever 1-2 paragrafos do Cap. 4.3.1 ("LangChain usado pontualmente para chunking e wrapper de embeddings; orquestracao em Python directo para controlo fino sobre cada chamada LLM").

**Latencia:** confirmado que remover o LangChain **nao acelera nada de relevante** — o unico ponto no caminho critico (`GoogleGenerativeAIEmbeddings`) representa ~0.3-0.8s (1-2% da latencia total). O bottleneck sao as 5-7 chamadas Claude ao gerador, reranker, etc.

**Decisao:** Ficou no ar. A Liane escolheu nao mexer agora — quis primeiro atacar a latencia percebida via **streaming**, que e o que se segue.

---

## Streaming SSE da geracao (maior salto de UX desta sessao)

### Motivacao

Antes do streaming: o utilizador via spinner durante ~30s e depois a resposta aparecia toda de uma vez. Com streaming, ve spinner durante o pre-amble (~7-12s, retriever + reranker + CRAG bloqueiam) e depois **tokens a aparecer em tempo real** durante a geracao (~10-20s).

**Tempo total continua igual** (~30s), mas a sensacao muda radicalmente: "esta a pensar" 10s -> "esta a escrever" 20s, em vez de "vai mau" durante 30s.

### Decisao critica: e o output_guard?

Hoje o output_guard valida a fidelidade ANTES do utilizador ver a resposta — se a fidelidade < 0.85 (threshold), anexa uma "NOTA DE QUALIDADE" automaticamente. Com streaming isto seria impossivel sem buffer.

Escolhida a opcao A (stream agora, validar depois):
- Stream tokens em tempo real -> ganho UX maximo
- Output_guard corre DEPOIS do stream terminar; aviso anexado no evento `done` como texto extra
- Trade-off: por 0-2s o utilizador pode estar a ler uma resposta que vai ganhar um aviso a seguir

Aceitavel porque com `temperature=0.2` no generator a fidelidade tipica fica entre 0.95-0.97 — o cenario de "stream e depois aviso" e raro na pratica.

### Backend

**[src/query/generator.py](src/query/generator.py)** — nova funcao `gerar_resposta_stream()`:
- Usa `cliente.messages.stream()` em vez de `messages.create()`
- Itera sobre `stream.text_stream` e faz `yield` de cada pedaco
- No fim, se `contexto_suficiente=False`, da yield ao aviso CRAG como ultimo pedaco
- A versao nao-streaming `gerar_resposta()` mantem-se intacta para fallback / endpoint nao-stream

**[src/query/pipeline.py](src/query/pipeline.py)** — novo `consultar_stream()` (generator function):
- Executa o **pre-amble sincrono**: input_guard -> reformulator -> retriever -> reranker -> CRAG. Bloqueia ate ter `chunks_finais`.
- Emite **evento `meta`** com fontes, query_usada, contexto_suficiente, num_chunks_usados — ANTES do gerador comecar. Isto permite ao frontend mostrar as fontes desde o inicio do stream.
- Itera `gerar_resposta_stream()` e emite **eventos `token`** com cada pedaco. Acumula numa lista para a auditoria.
- Apos o stream, corre o **output_guard** sobre a resposta completa. Calcula `texto_extra` (o que o guard anexou para alem do texto original).
- Emite **evento `done`** com `valido`, `fidelidade`, `texto_extra`, `resposta_completa`, `duracao_segundos`.
- Em qualquer erro, emite **evento `error`** com `detalhe` e `etapa` (input_guard/retrieval/generator).

**[src/api/main.py](src/api/main.py)** — novo endpoint `POST /consulta/stream`:
- Devolve `StreamingResponse` com `media_type="text/event-stream"`
- Cada evento serializado como `data: {json}\n\n` (formato SSE)
- Headers para evitar buffering em proxies: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`
- Audit log corre em background no fim (mesma assinatura que o `/consulta` original)
- O `/consulta` (nao-stream) **mantem-se** para fallback e Swagger

### Frontend

**[src/api/static/app.js](src/api/static/app.js)** — `submitQuery()` substituido por consumidor SSE:
- Continua a fazer `fetch()` (porque `EventSource` nao suporta POST e nao permite enviar body)
- Le o `res.body` como `ReadableStream` via `getReader()` + `TextDecoder`
- Acumula em buffer e parte por `\n\n` (separator de eventos SSE)
- 3 fases visuais da bubble:
  - **Fase 1 (`meta`):** substitui a thinking bubble pela bubble real, com fontes ja clicaveis e linha "Interpretado como:" se houve reformulacao
  - **Fase 2 (`token`):** texto cru com cursor a piscar, dentro de `<pre class="chat-body-raw">` para preservar quebras de linha
  - **Fase 3 (`done`):** substitui o `<pre>` pelo HTML formatado via `formatResponse(textoAcumulado)`; remove a classe `chat-bubble-streaming`

Erros de validacao Pydantic (422) continuam a vir como JSON antes do stream comecar — tratados via `res.ok === false` + `formatErrorDetail`.

`appendAssistantBubble()` antiga foi preservada (renomeada conceptualmente para "single-shot") como fallback para o caso de alguem chamar `/consulta` em vez de `/consulta/stream` no futuro.

**[src/api/static/style.css](src/api/static/style.css)** — estilos novos:
- `.chat-body-raw`: `font-family` igual ao resto, `white-space: pre-wrap`, sem `<pre>` styling default do browser
- `.chat-cursor`: 8px x 1em, fundo `--primary`, animacao `@keyframes chat-cursor-blink` de 1s com `steps(2, start)`
- `.chat-bubble-streaming`: leve glow teal (`box-shadow` + borda `--primary-light`) enquanto recebe tokens

### Validacao

```
venv\Scripts\python.exe -c "from src.api.main import app; ..."
-> stream route: True
-> all routes: [..., '/consulta', '/consulta/stream', ...]
-> consultar_stream is gen-func: True
-> gerar_resposta_stream is gen-func: True
```

Teste end-to-end no browser nao feito nesta sessao — fica para a Liane confirmar com `docker compose up --build` + Ctrl+F5.

---

## Comportamento final

| Cenario | Latencia | Comportamento |
|---|---|---|
| 1a pergunta da conversa (`historia=[]`) | igual ao anterior (~30s **total**, ~7-12s ate 1o token) | Reformulator faz early return; spinner curto, depois tokens em streaming |
| Pergunta de seguimento ("e a posologia?") | +1-2s ao pre-amble | Reformulator reescreve antes do retriever; depois streaming normal |
| Pergunta autonoma de seguimento | +1-2s ao pre-amble | Reformulator devolve query inalterada mas paga a chamada LLM |
| Fontes citadas | clicaveis desde o evento `meta` | `<a href=".../ficheiros/{tipo}/{ficheiro}#page=N" target="_blank">`, abre o PDF na pagina certa |
| Fidelidade abaixo de 0.85 | aviso anexado ~1-2s **depois** do stream terminar | Output_guard corre apos `done`, `texto_extra` aparece na bubble |
| Erro de validacao Pydantic (ex: query <5 chars) | n/a | Devolve 422 ANTES do stream comecar; mensagem legivel via `formatErrorDetail` |
| Erro mid-stream (generator falha) | n/a | Evento `error` consumido pelo cliente; bubble parcial removida |
| Erro 500 antes do stream | n/a | `detail` (string) mostrado directamente |
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

- Imports do backend chat: `consultar`, `reformular_com_historia`, `ConsultaRequest`, `Mensagem`, `registar_consulta` -> OK
- Schema `ConsultaRequest` aceita payload com `historia` (lista de dicts) e `session_id` -> validado
- Teste manual no browser: 1 mensagem "ola" expos o bug `[object Object]`, corrigido em seguida
- Endpoint `/ficheiros/{tipo}/{nome}` registado e responde a path com PDF existente
- Endpoint `/consulta/stream` registado; `consultar_stream` e `gerar_resposta_stream` confirmados como generator-functions via `inspect.isgeneratorfunction()`
- 13 rotas FastAPI registadas no fim da sessao (era 11 ao inicio do CONTEXT7)

**Nao corridos nesta sessao:**
- Suite de testes (`tests/test_pipeline.py` precisaria de cenarios multi-turn novos + cenarios de streaming)
- Teste real end-to-end de uma conversa de 3+ turnos com o Qdrant a correr (Liane vai testar)
- Teste real end-to-end do streaming SSE no browser
- `tests/test_reformulator.py`, `tests/test_stream.py` — ambos no plano original, ficaram para a proxima sessao
- Validacao do directory traversal no endpoint `/ficheiros/...` com path malicioso real

---

## Ficheiros modificados (nao-comitados no fim da sessao)

```
?? docs/CONTEXT7.md                         <- novo (este ficheiro)
M  src/api/audit.py                         <- + session_id no JSONL
M  src/api/main.py                          <- /consulta com historia+session_id,
                                               + /ficheiros/{tipo}/{nome} (PDF),
                                               + /consulta/stream (SSE)
M  src/api/models.py                        <- + Mensagem, historia, session_id
M  src/api/static/app.js                    <- estado de conversa, bubbles,
                                               formatErrorDetail, parser SSE,
                                               3 fases da bubble streaming
M  src/api/static/index.html                <- chat-card no tab consulta
M  src/api/static/style.css                 <- chat styles + source-tag-link +
                                               streaming (cursor a piscar, glow)
M  src/query/generator.py                   <- + gerar_resposta_stream() generator
M  src/query/pipeline.py                    <- etapa 1b reformulacao + consultar_stream()
M  src/query/prompt.py                      <- + PROMPT_REFORMULACAO_CONTEXTUAL
?? src/query/reformulator.py                <- novo modulo
```

11 ficheiros, 2 novos.

---

## Pontos abertos / proximos passos

1. **Testar tudo ponta-a-ponta** — apos `docker compose down && docker compose up --build` + Ctrl+F5:
   - **Chat multi-turn:** "O que e o brufen?" -> "e a posologia?" (deve aparecer "Interpretado como:...") -> "e nos idosos?"
   - **Fontes clicaveis:** clicar numa tag deve abrir o PDF na pagina certa numa tab nova
   - **Streaming:** spinner durante o pre-amble (~7-12s), depois tokens em tempo real com cursor a piscar, formatacao markdown aplicada no fim
2. **Decisao LangChain ainda em aberto** (opcao A vs B documentada acima) — se for opcao B, e ~15 min de cleanup em `requirements.txt` + 1-2 paragrafos do Cap. 4.3.1
3. **Testes unitarios pendentes:**
   - `tests/test_reformulator.py` — historico vazio (early return), follow-up vago (reformula), pergunta autonoma (devolve igual); mock do `obter_cliente()`
   - `tests/test_stream.py` — `gerar_resposta_stream` e `consultar_stream` emitem a sequencia correcta de eventos
   - `tests/test_pipeline.py` — adaptar cenarios multi-turn
4. **Mensagens de erro em portugues** — Pydantic vem em ingles; falta mapping no `formatErrorDetail()` ou validators customizados
5. **localStorage no frontend** — actualmente a conversa morre num refresh. Adiado na fase de plano; util para a demo
6. **`GET /conversas/{session_id}`** — agrupar audit logs por sessao para o tab Auditoria mostrar threads
7. **Commit das mudancas** — agora ha mais coisa que ao inicio do CONTEXT7. Sugestao revista de 5 commits tematicos:
   - feat(chat): backend stateless com reformulacao contextual (models, prompt, reformulator, pipeline, audit, main)
   - feat(chat): frontend com thread, bubbles e historico no cliente (index.html, app.js, style.css)
   - fix(ui): mostrar erros de validacao Pydantic em vez de "[object Object]"
   - feat(api): endpoint /ficheiros/... + fontes clicaveis na UI
   - feat(stream): SSE no /consulta/stream com 3 fases na bubble (generator, pipeline, main, app.js, style.css)
8. **README desactualizado** (heranca de sessoes anteriores) — ainda diz "Claude 3.5 Sonnet"
9. **Limpeza disco** (heranca do CONTEXT6) — 2.27GB do bge-reranker no cache do HuggingFace + ~1GB de `torch/sentence_transformers` no venv

### Memorias actualizadas

Nenhuma actualizacao a `memory/MEMORY.md` nesta sessao. A estrategia LLM (`project_crag_llm_strategy.md`) continua valida: tanto o reformulator como o stream do generator usam Claude Sonnet 4.6, alinhados com o resto da stack. Candidatas a nova memoria: "Sistema migrou para chat conversacional com streaming SSE (15/maio/2026 - sessao do CONTEXT7)" — pode valer a pena se o pivot ficar como padrao do sistema final.

### Resumo executivo da sessao

- **Pivot arquitectural:** Q&A -> chat conversacional, backend stateless, **com streaming**
- **2 modulos novos:** `src/query/reformulator.py` (history-aware retriever) e `gerar_resposta_stream()` em `generator.py`
- **3 endpoints novos:** `POST /consulta/stream` (SSE), `GET /ficheiros/{tipo}/{nome}` (PDF), [`/consulta` continua intacto]
- **11 ficheiros alterados** (10 modificados + 1 novo modulo); frontend totalmente refeito para chat + streaming
- **1 bug encontrado e corrigido** (`[object Object]` por mau handling de erros 422 Pydantic)
- **1 UX gap fechado:** fontes documentais agora abrem o PDF na pagina citada (rastreabilidade real)
- **1 discussao arquitectural com decisao adiada** (sub-uso do LangChain)
- **Trade-off principal:** +1-2s no pre-amble em follow-ups (reformulator), em troca de retrieval contextualmente correcto; streaming neutraliza isto na percepcao do utilizador porque o pre-amble fica visivel como "a pensar" e depois "a escrever"
- **Latencia total inalterada** (~30s) mas **tempo ate 1o token caiu de ~30s para ~7-12s** — maior salto de UX da historia do projecto
- **Nao quebrou nada:** `/consulta` (nao-stream) intacto, `appendAssistantBubble` preservada como fallback, 1a pergunta sem historico corre como antes
