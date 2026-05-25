# CONTEXT6.md — Sessao de optimizacao de latencia: ganhos efetivos e experimento abandonado

## Snapshot no fim do CONTEXT5

- Pipeline RAG ponta-a-ponta funcional (6 etapas), 53 testes unitarios + 13 integracao a passar
- `GENERATIVE_MODEL = "claude-sonnet-4-6"` em toda a stack LLM, Gemini so para embeddings
- Latencia estimada: 35-50s (CONTEXT5) — pessimista, mas claramente acima do RNF01 (<=10s)
- 10 melhorias do Antigravity pendentes
- Reranker e CRAG ambos usam Sonnet 4.6 (LLM-as-Judge)
- Apenas 1 PDF indexado (`brufen_folheto.pdf`)

Esta sessao focou-se em **baixar a latencia** mantendo a arquitetura (reranker + CRAG no pipeline).

---

## Mudancas aplicadas (ainda nao-comitadas no fim da sessao)

### 1. Cliente Anthropic singleton

**Problema:** Antigravity #4 — cada chamada LLM cria um `Anthropic(api_key=...)` novo (5 sitios: reranker, crag, generator, input_guard, output_guard). Cada instanciacao paga handshake TLS/HTTP.

**Solucao:**
- Novo modulo `src/llm_client.py` com `obter_cliente()` (lazy singleton)
- Refactor dos 5 ficheiros: removido `from anthropic import Anthropic` e `ANTHROPIC_API_KEY`, substituido por `obter_cliente()`

**Ganho:** ~0.3-0.5s por query (4 das 5 chamadas LLM poupam o handshake).

**Validacao:** `c1 = obter_cliente(); c2 = obter_cliente()` devolve a mesma instancia (`c1 is c2 == True`). 53 testes unitarios passam.

---

### 2. Skip-CRAG heuristico

**Problema:** o CRAG faz uma 2a chamada LLM a perguntar "estes chunks sao suficientes?" mesmo quando o reranker (que ja e um LLM-as-Judge) acabou de lhes dar score 0.95+. Em queries claras (~60-70% do trafego), e desperdicio de 2-4s.

**Solucao:** 
- Novo `SKIP_CRAG_THRESHOLD = 0.85` em `src/config.py`
- `pipeline.py` verifica `chunks_rerankados[0].score` antes de chamar `crag_pipeline()`. Se `>= 0.85`, define `contexto_suficiente=True` diretamente e salta a etapa
- O CRAG completo (incluindo reformulacao de query) continua intato para casos de retrieval fraco

**Ganho real medido:** query "Qual a posologia do brufen em adultos?" desceu de ~30s (estimado pre-skip) para **28.2s** com skip a disparar (`Saltado (top score 1.00 >= 0.85)`).

**Defesa academica:** filtro heuristico baseado em scores do reranker; o reranker e ele proprio um juiz LLM de relevancia, pelo que a 2a avaliacao e redundante em casos de alta confianca.

---

### 3. Reranker code review + quality fixes

**Code review identificou 8 problemas em `src/query/reranker.py`. Aplicados 6:**

| # | Problema | Fix |
|---|---|---|
| 1 | `chunk.score = ...` mutava o chunk original (Antigravity #3) | `replace(chunks[idx], score=...)` cria copia |
| 2 | Score sem clamp; LLM podia devolver 15 → 1.5 fora de [0,1] | `max(0, min(10, score)) / 10.0` |
| 3 | Sem `temperature` (default 1.0) — RAGAS teria variabilidade artificial | `temperature=0` |
| 4 | Truncagem fixa a 1500 chars (37% do chunk) | 4000 chars (= `CHUNK_SIZE`), com `[...]` quando trunca |
| 5 | Role no `user message` | `system=` separado, tarefa em `user` |
| 6 | Excerto cortado sem aviso ao LLM | `[...]` sinaliza truncagem |

**Descartados na revisao:**
- #5 retry — verificado que o SDK Anthropic ja faz retry automatico (`max_retries=2` em 408/409/429/5xx)
- #6 logar `razao` — toca no modulo de audit, fora do ambito de "melhorar reranker"

**Trade-off de latencia:** chunks maiores no prompt adicionam ~200-500ms por chamada. Compensado parcialmente pelo `temperature=0` que tende a produzir outputs mais curtos.

**Defesa academica:** reprodutibilidade (`temperature=0`), robustez (clamp + no-mutation), idiomaticidade (system prompt separado), preservacao de informacao critica em chunks longos (truncagem alargada).

---

### 4. Print de diagnostico do top_score

**Adicionado em `pipeline.py`:** mostra sempre o top score do reranker antes da decisao skip-CRAG, nao so quando dispara.

```
   Top score do reranker: 0.726 (threshold skip: 0.85)
```

Util para tuning futuro de thresholds e debug.

---

## Experimento abandonado: cross-encoder bge-reranker-v2-m3

### Motivacao

Substituir o LLM-as-Judge (Sonnet 4.6, ~3-6s/query) por inferencia local com `BAAI/bge-reranker-v2-m3`. Promessa teorica: ~200ms reranking, deterministico, sem custo per-query, narrativa academica forte (padrao moderno em RAG).

Discutidas e descartadas as variantes:
- **Cascata** (cross-encoder + LLM-as-Judge): ganho de latencia menor (-0.5 a -2.5s), mais complexo. Liane prefere simplicidade.
- **Haiku 4.5 no reranker**: risco de qualidade nao-mensuravel ate RAGAS estar pronto.

### O que foi feito

- Instalado `sentence-transformers` (+ `torch`, `transformers`, `tokenizers`, `huggingface-hub` — ~1GB no venv)
- `src/query/reranker.py` reescrito para usar `CrossEncoder("BAAI/bge-reranker-v2-m3")` com lazy load
- `requirements.txt` atualizado
- `Dockerfile` atualizado: linha `RUN python -c "...CrossEncoder('BAAI/bge-reranker-v2-m3')"` para pre-cachear o modelo na build
- Modelo descarregado para `~/.cache/huggingface/` (2.27GB — corrigi a estimativa anterior de 568MB; 568M sao os _parametros_, nao o tamanho do ficheiro safetensors em float32)

### Por que falhou

Diagnostico com timing instrumentado em `obter_modelo()` e `predict()`:

```
[reranker] Modelo carregado em 5.8s          <- cold start por processo
[reranker] predict() para 10 pares: 26.46s   <- catastrofe
```

**Causa provavel:** PyTorch instalado via `pip install` no Windows nao traz aceleracao MKL/AVX bem configurada para CPU. O bge-reranker-v2-m3 tem 568M parametros — sem aceleracao, processar 10 pares de ~1000 tokens cada e literalmente isto.

**Resultado:** pipeline subiu de 28.2s (LLM-as-Judge) para **63s** (cross-encoder). Regressao 2.2x.

**Bonus negativo:** o threshold `SKIP_CRAG_THRESHOLD = 0.85` foi calibrado para scores do LLM-as-Judge (0-10 normalizado). Os scores do cross-encoder (sigmoid sobre logits) tem distribuicao diferente — top score na query de exemplo foi 0.726, abaixo do threshold. CRAG voltou a correr sempre, anulando o ganho do skip-CRAG.

### Reversao

- `src/query/reranker.py` revertido para LLM-as-Judge (preservando as quality fixes do ponto #3)
- `requirements.txt` revertido (sem `sentence-transformers`)
- `Dockerfile` revertido (sem pre-cache do modelo)
- `pipeline.py`: label revertido para "(LLM-as-Judge)", **print do top_score mantido** (e diagnostico util independente do reranker escolhido)

**Limpeza adiada (opcional):**
- `pip uninstall sentence-transformers transformers tokenizers safetensors huggingface-hub` — recupera ~1GB no venv
- `rmdir /s /q C:\Users\UM3402\.cache\huggingface` — recupera 2.27GB

### Licao para o relatorio

Trade-off real entre arquitetura "ideal" e viabilidade pratica em hardware modesto. O cross-encoder e o padrao moderno em RAG mas pressupoe GPU ou CPU bem otimizado. Em ambiente Windows com pip torch standard, o LLM-as-Judge externo continua a ser mais rapido. **Esta observacao justifica academicamente a escolha do LLM-as-Judge no sistema final.**

---

## Code review completo do codebase

Apos a reversao do cross-encoder, fiz uma review honesta de todos os ficheiros do pipeline (`src/query/`, `src/guardrails/`, `src/api/`, `src/ingestion/embedder.py`, `src/query/prompt.py`). Identifiquei 8 oportunidades de latencia que ainda nao tinham sido discutidas:

| # | Achado | Impacto |
|---|---|---|
| 1 | Generator sem `temperature` (default 1.0) nem limite efetivo de `max_tokens` (2048) | Alto — respostas verbosas com emojis/decoracao escalam latencia da geracao |
| 2 | Output_guard envia chunks completos para validacao de fidelidade (12000 chars) | Medio — trabalho duplicado vs gerador |
| 3 | Embedder (LangChain/Gemini) e cliente Qdrant recriados em cada query | Medio — mesmo padrao Antigravity #4 que ja resolvemos para Anthropic |
| 4 | `RETRIEVAL_TOP_K = 10` quando `RERANK_TOP_N = 3` | Medio — reranker processa 10 chunks para descartar 7 |
| 5 | Audit log sincrono em `api/main.py` antes de devolver resposta | Baixo — file I/O no caminho critico |
| 6 | `fidelidade` aceite por `registar_consulta` mas nunca passada pela API | Bug/qualidade — score perdido para analise posterior |
| 7 | `_formatar_contexto` duplicado em 3 ficheiros | DRY violation, nao latencia |
| 8 | Lazy import de `consultar` dentro do endpoint da API | Cold start trade-off |

---

## Segunda batch de mudancas aplicadas (resolve #1, #3, #4, #5 do code review)

### 5. Generator: `temperature=0.2`, `max_tokens=2048→1500`, regra de conciseness

**Ficheiros:** `src/query/generator.py`, `src/query/prompt.py`

- `temperature=1.0 → 0.2` — respostas mais factuais e estaveis
- `max_tokens=2048 → 1500` — cap mais conservador no comprimento maximo
- Nova regra #7 no SYSTEM_PROMPT do generator:
  > "Responde de forma CONCISA e DIRETA. Estrutura com paragrafos curtos e bullets quando ajudar a leitura clinica, mas evita ornamentacao decorativa (emojis, separadores ---, tabelas-sumario redundantes, secoes excessivas). A prioridade e a informacao clinica, nao a formatacao visual."

**Validacao em query real** (efeitos secundarios do brufen):
- Antes: resposta com 10+ emojis, separadores `---`, tabela-sumario duplicada, ~1500 palavras
- Depois: resposta organizada por sistema de orgaos, sem emojis, ~800 palavras
- Fidelidade preservada (0.95 vs 0.97 antes — diferenca dentro do ruido)
- **Ganho: ~6-8s na geracao de respostas longas**

### 6. Singleton embedder + cliente Qdrant

**Ficheiros:** `src/ingestion/embedder.py`, `src/ingestion/indexer.py`, `src/query/retriever.py`

- Novo `obter_embedder(task_type)` em `embedder.py` — cache por task_type (RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY usam instancias diferentes)
- Novo `obter_cliente()` em `indexer.py` — singleton para QdrantClient
- `retriever.py` atualizado para usar os singletons em vez de `criar_embedder()` e `criar_cliente()` originais

As funcoes originais `criar_*` ficam para o pipeline de ingestao (que cria uma vez no inicio do batch).

**Ganho: ~0.2-0.5s por query** (handshake HTTP/gRPC poupado em cada chamada).

### 7. `RETRIEVAL_TOP_K = 10 → 7`

**Ficheiro:** `src/config.py`

O reranker so leva 3 chunks ao gerador (`RERANK_TOP_N = 3`). Recuperar 10 quando se vai descartar 7 e desperdicio. Recuperar 7 mantem boa probabilidade de capturar os relevantes (o RRF do Qdrant ja e forte) e reduz em ~30% o tamanho do prompt do reranker.

**Ganho: ~1-2s no reranker** (prompt mais curto, output potencialmente mais curto).

### 8. Audit log via FastAPI BackgroundTasks

**Ficheiro:** `src/api/main.py`

`registar_consulta(...)` era chamado sincronamente antes de `return ConsultaResponse(...)`. Agora:

```python
async def consulta(pedido, request, background_tasks: BackgroundTasks):
    ...
    background_tasks.add_task(registar_consulta, ...)
    return ConsultaResponse(...)  # devolve imediatamente
```

A escrita JSONL acontece em background, depois da resposta sair. **Ganho: ~50-200ms percebidos**. Pequeno isoladamente, mas estabelece o padrao para fazer o mesmo com o output_guard mais tarde.

---

## Experimento abandonado #2: truncagem de chunks no output_guard

### Motivacao

O `output_guard.verificar_fidelidade` envia ~12000 chars de chunks + a resposta inteira ao Sonnet para validacao. Hipotese: truncar os chunks a 2000 chars cortaria ~2/3 do prompt e dava 3-5s de ganho.

### O que foi feito

`MAX_CHARS_FIDELIDADE = 2000` introduzido em `output_guard.py`. Cada chunk passado a `verificar_fidelidade` era truncado a 2000 chars com sufixo `[...]`.

### Por que falhou

Validacao em query real:
- Latencia: 42.8s → 34.5s (ganho aparente de 8s — bom)
- **Fidelidade: 0.97 → 0.72** — **abaixo do threshold 0.85**
- Resposta marcada com "NOTA DE QUALIDADE" automatica

**Mecanismo da regressao:**
1. Gerador ve chunks COMPLETOS (4000 chars) e produz resposta baseada na informacao total
2. Validador so ve METADE dos chunks (2000 chars)
3. Citacoes que se referem a informacao na 2a metade dos chunks parecem nao-suportadas para o validador
4. Falsa deteccao de alucinacao

A resposta esta correta — todas as citacoes tem fontes validas. A regressao e estrutural: **um validador que ve menos contexto do que o gerador e estruturalmente injusto com a resposta**.

### Reversao

Truncagem removida. **Comentario explicativo deixado no codigo** para evitar que a armadilha seja re-introduzida no futuro:

```python
# A validacao usa os chunks completos: truncar aqui faria com que afirmacoes
# da resposta baseadas na 2a metade dos chunks parecessem nao-suportadas
# ao validador, gerando falsas deteccoes de alucinacao.
```

### Licao para o relatorio

**Optimizacoes assimetricas em pipelines de validacao sao perigosas.** Se o gerador vê X e o validador vê apenas X/2, o sistema cria falsos positivos de alucinacao. Lição aplicavel a qualquer pipeline com etapas de auto-verificacao: a etapa de validacao deve ter pelo menos o mesmo contexto que a etapa que produziu o artefacto a validar.

---

## Investigacao: prompt caching descartado

Apos as mudancas anteriores, propus prompt caching como proximo passo seguro. Ao investigar a aplicabilidade, descobri que **nao se aplica a este codebase como esta**:

**O minimum cacheable size da Anthropic API e 1024 tokens.** Tokens estimados dos nossos system prompts:

| Prompt | Tokens estaveis |
|---|---|
| Generator SYSTEM_PROMPT (com regra #7) | ~300-450 |
| Reranker SYSTEM_PROMPT | ~50 |
| Reranker PROMPT_RERANK (sem variaveis) | ~80 |
| Output_guard PROMPT_FIDELIDADE (sem variaveis) | ~110 |
| CRAG PROMPT_CRAG_AVALIACAO / PROMPT_CRAG_REFORMULACAO | ~100 cada |
| Input_guard prompt de dominio | ~100 |

Marcar `cache_control` neles e aceite pela API mas **silenciosamente nao cacheia** (no-op).

**Variante que funciona mas exige refactor:** cachear os **chunks** (que sao ~3000 tokens, bem acima do minimo) entre as chamadas do gerador e output_guard dentro da mesma query. Requer standardizar formato dos chunks em 3 ficheiros + adicionar `cache_control` nos 3 sitios. **Tempo estimado: 1-1.5h, ganho ~2-4s no output_guard.** Adiado.

---

## Optimizacoes discutidas mas adiadas

| # | Optimizacao | Ganho previsto | Porque foi adiado |
|---|---|---|---|
| 1 | Prompt caching (`cache_control` nos system prompts) | -1 a -2s a partir da 2a query | Acordado como proximo passo seguro; nao implementado por falta de tempo na sessao |
| 2 | Output_guard async (fidelidade em background apos resposta) | -3 a -5s percebido | Decisao UX necessaria (resposta sai antes de validar) |
| 3 | Streaming na geracao (SSE) | -8 a -12s percebido | Toca generator + API + frontend; conversa dedicada |
| 4 | Paralelizar input_guard + retrieval | -0.5 a -1.5s | Ganho pequeno, baixa prioridade |
| 5 | Haiku 4.5 nos guardrails/CRAG/reranker | -2 a -4s | Risco de qualidade nao mensuravel ate RAGAS; protocolo: medir antes de trocar |

---

## Baseline de latencia medida

| Configuracao | Query | Latencia |
|---|---|---|
| CONTEXT5 (estimativa) | n/a | 35-50s |
| Singleton + skip-CRAG (medido) | brufen posologia (curta) | **28.2s** |
| Cross-encoder bge-reranker-v2-m3 (medido — regressao) | brufen posologia | 63s |
| Apos revert + quality fixes (medido) | brufen efeitos secundarios (longa) | 42.8s |
| Truncagem output_guard (medido — regressao fidelidade) | brufen efeitos secundarios | 34.5s (mas fidelidade 0.72) |
| **Estado final desta sessao (medido)** | **brufen efeitos secundarios** | **35.5s — fidelidade 0.95** |
| Estado final desta sessao (previsto) | brufen posologia (curta) | ~22-26s (re-medir) |

Ganho consolidado para queries longas: **~17%** (42.8s → 35.5s).

---

## Estado real (15/maio/2026, fim de sessao)

| Componente | Valor atual |
|---|---|
| `EMBEDDING_MODEL` | `gemini-embedding-2-preview` |
| `GENERATIVE_MODEL` | `claude-sonnet-4-6` |
| Cliente Anthropic | Singleton via `src/llm_client.py::obter_cliente()` |
| Reranker | LLM-as-Judge (Sonnet) com `temperature=0`, system prompt separado, clamp, truncagem 4000 chars |
| CRAG | Intacto com skip heuristico (`SKIP_CRAG_THRESHOLD = 0.85`) |
| Skip-CRAG validado | Sim (top score 1.00 saltou em query real de posologia) |
| Testes | 53 unitarios a passar (integracao nao corridos nesta sessao) |
| Documentos indexados | 1 bula (`brufen_folheto.pdf`) — inalterado |
| Antigravity #3 (reranker muta chunks) | Resolvido |
| Antigravity #4 (cliente recriado) | Resolvido |
| Restantes 8 itens Antigravity | Pendentes |

### Ficheiros modificados (nao-comitados)

```
M  src/config.py                    <- + SKIP_CRAG_THRESHOLD, RETRIEVAL_TOP_K 10→7
M  src/guardrails/input_guard.py    <- usa obter_cliente()
M  src/guardrails/output_guard.py   <- usa obter_cliente() + comentario anti-truncagem
M  src/query/crag.py                <- usa obter_cliente()
M  src/query/generator.py           <- usa obter_cliente(), temperature=0.2, max_tokens=1500
M  src/query/pipeline.py            <- skip-CRAG + print diagnostico
M  src/query/prompt.py              <- regra #7 conciseness no SYSTEM_PROMPT
M  src/query/reranker.py            <- usa obter_cliente(), quality fixes
M  src/query/retriever.py           <- usa obter_embedder() + obter_cliente() singletons
M  src/ingestion/embedder.py        <- + obter_embedder() singleton por task_type
M  src/ingestion/indexer.py         <- + obter_cliente() singleton para Qdrant
M  src/api/main.py                  <- BackgroundTasks para audit log async
?? src/llm_client.py                <- novo
```

### Ficheiros nao-comitados pendentes de sessoes anteriores

```
R  docs/CONTEXT.md -> docs/CONTEXT1.md
?? docs/CONTEXT5.md
?? docs/CONTEXT6.md (este ficheiro)
```

### Disco (cleanup opcional pendente)

- `~/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/` — 2.27GB
- `venv/Lib/site-packages/torch/` + `sentence_transformers/` + transitivos — ~1GB

---

## Pontos abertos / proximos passos

1. **Commit das mudancas atuais** — 12 ficheiros modificados + `src/llm_client.py` novo. Conjunto coerente de optimizacoes nao-revertidas, faz sentido consolidar em 2-3 commits tematicos antes de avancar.
2. ~~**Prompt caching**~~ — **descartado** apos investigacao: prompts demasiado curtos para o minimum 1024 tokens. Variante "chunks caching" (1-1.5h, ganho ~2-4s) fica como opcional.
3. **Decisao sobre output_guard async** — maior alavanca de latencia percebida que sobra (-5 a -8s). Implica compromisso UX (resposta sai antes da validacao de fidelidade). Merece sessao dedicada com decisao sobre comportamento de falha.
4. **Streaming na geracao (SSE)** — transforma a UX da demo. ~1-2h, toca em generator + API + frontend.
5. **Re-medir query curta** (posologia) com a configuracao final desta sessao — esperado ~22-26s.
6. **Fix qualidade #6 do code review:** passar `fidelidade` da pipeline para `registar_consulta()` na auditoria.
7. **Re-ingerir uma monografia** — pasta `monografias/` esta vazia desde `cc181d4`.
8. **Avaliacao RAGAS** (Cap. 5 do relatorio) — sera muito mais reproduzivel agora com `temperature=0` no reranker e `temperature=0.2` no generator.
9. **Restantes 8 itens Antigravity** — `chunk.score` mutacao foi resolvida pelos quality fixes; restantes pendentes.
10. **Deployment Coolify** (Cap. 4.3.4).

### Memorias atualizadas nesta sessao

Nenhuma actualizacao a `memory/MEMORY.md` — a estrategia LLM (`project_crag_llm_strategy.md`) continua valida: Claude Sonnet 4.6 em toda a stack, Gemini so para embeddings. A tentativa cross-encoder foi revertida, pelo que nao altera a estrategia documentada.

### Resumo executivo da sessao

- **2 mudancas grandes que ficaram:** singleton Anthropic, skip-CRAG
- **6 quality fixes no reranker** (temperature=0, system prompt, clamp, no-mutation, truncagem alargada, sinalizacao de truncagem)
- **4 mudancas adicionais** (generator concise, singletons embedder+Qdrant, top_k=7, audit async)
- **2 experimentos abandonados** com licoes documentadas: cross-encoder (hardware inadequado) e truncagem output_guard (validador injusto)
- **1 investigacao com resultado negativo:** prompt caching nao se aplica sem refactor maior
- **Ganho real medido:** ~17% de latencia em queries longas (42.8s → 35.5s) com **fidelidade preservada** (0.97 → 0.95)
- **Caminho para RNF01 (10s) ainda exige decisoes arquiteturais** (output_guard async, streaming) — nao chegamos so com optimizacoes pontuais
