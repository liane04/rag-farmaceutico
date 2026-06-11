# CONTEXT10.md — Producao em baixo, corpus real, apagar documentos, citacoes numeradas e polimento UX

> Data: 2026-06-10/11. Cobre tudo desde o fim do CONTEXT9 (Parte 4 — modo local
> viavel com qwen2.5:3b). Sessao longa de "preparar para entregar": guard de
> dominio corrigido, otimizacoes de latencia local, incidente da suite de testes,
> corpus expandido para 14 documentos, funcionalidade de apagar documentos,
> citacoes numeradas [n], e uma rodada grande de UX. **Tudo uncommitted no fim.**

## Snapshot no fim do CONTEXT9

- Commit no `main` (local e remotos): `320a863` — switch LLM + fix QDRANT_HOST,
  ja **deployed em producao** via force-push.
- Modo local viavel (qwen2.5:3b-instruct + format=json), ~6 min/consulta em CPU.
- Corpus: 1 PDF (brufen_folheto.pdf, 12 chunks). Modo persistido: online.
- Por commitar: trabalho da Parte 4 (8 ficheiros) + CONTEXT9.md.

---

## 1. Producao esta EM BAIXO (infra, nao e nosso)

A Liane referiu que "a versao do servidor da Teclab nao esta a dar". Diagnostico:

- `https://prj-rag-ld.teclab.pt/` — **TCP timeout na porta 443**; o DNS resolve
  (`57.129.67.102`) mas nada aceita ligacoes. Nem o proxy do Coolify responde
  (um 502 indicaria app morta com proxy vivo; HTTP 000 = maquina/firewall/proxy).
- **Nao foi o nosso deploy** — codigo nenhum derruba o TCP do host.
- Acao: avisar o Ricardo (alcada dele). Mensagem pronta na conversa.
- **Quando voltar:** testar o login em producao — o `override=False` do commit
  `320a863` inverteu a precedencia (env vars do Coolify passam a ganhar ao
  `.env` montado); se as env vars da UI do Coolify estiverem desatualizadas,
  o login pode falhar (o fix de maio `c165f80` dependia do `.env` ganhar).
- Decisao da Liane: a apresentacao sera **so por video**, producao nao sera
  mostrada — risco do toggle local em prod (sem Ollama) aceite conscientemente.

## 2. Guard de dominio rejeitava marcas que o modelo nao conhece

- Sintoma (browser, modo local): "o que e brufen?" → "Esta questao parece estar
  fora do dominio farmaceutico."
- Causa: com o switch agora completo (CONTEXT9 Parte 4), o input_guard corre no
  **qwen2.5:3b em modo local** — e o 3b nao conhece a marca "Brufen"; respondia
  literalmente `NAO`. (Ironia: antes do fix dos callsites isto nunca aparecia
  porque o guard ia sempre ao Claude — o bug mascarava a lacuna.)
- Fix no prompt do `_verificar_dominio` ([input_guard.py]): nomes comerciais/
  marcas SAO dominio farmaceutico mesmo desconhecidos; so responder NAO quando
  e claramente outro tema; **em caso de duvida → SIM** (fail-open; o resto do
  pipeline lida bem com queries sem documentos).
- Validado em local: brufen/ben-u-ron/ibuprofeno aceites; capital de Franca e
  mundial 2022 rejeitados. Validado tambem dentro do container.

## 3. Otimizacoes de latencia do modo local (e os limites honestos)

Pergunta da Liane: "nao da para diminuir o tempo do local? e so por ser o meu pc?"

- **Hardware dela:** Ryzen 5 5625U (6C/12T, serie U), **7.4 GB RAM**, iGPU Radeon
  inutil para o Ollama → inferencia 100% CPU. E ~80% da causa.
- **Descoberta importante:** `ollama ps` mostrava **CONTEXT 4096** — os prompts
  de CRAG/geracao/fidelidade (3 chunks × 4000 chars) excediam a janela e o
  Ollama **truncava em silencio** (lento E o modelo nem via o contexto todo;
  explica parte da fidelidade 0.5-0.6).
- Aplicado em [llm_client.py] e [crag.py]:
  - `num_ctx=8192` no ChatOllama (qwen2.5 suporta 32K);
  - `keep_alive="30m"` (modelo quente entre chamadas; recarregar custava 30-60s);
  - CRAG-avaliacao trunca chunks a **1200 chars em modo local**
    (`MAX_CHUNK_CHARS_LOCAL`) — julgar relevancia nao exige o texto completo.
- **Medicao por etapa** (consulta local, apos fixes): input_guard 63s (inclui
  load do modelo), retrieval 2s, **reranker 116s**, CRAG 29s, geracao 77s,
  fidelidade 69s (score 0.25 — juiz 3b instavel com contexto longo) →
  **TOTAL 355s** (vs ~380 antes; pouco ganho liquido).
- **Cortes adicionais propostos e ADIADOS pela Liane** ("nao facas nada ainda"):
  A) reranker heuristico em local (~-2 min); B) fidelidade com contexto truncado
  em local (~-40s e juiz mais estavel); C) skip-CRAG a 0.80 em local (~-30s).
- Servidor da Teclab seria mais rapido? Depende das specs (VPS tipico sem GPU ≈
  igual; so GPU muda de liga) — e producao **nem tem Ollama** instalado.
  Perguntar specs ao Ricardo se o modo local em prod interessar.

## 4. Incidente da suite de testes → padrao de config do OLLAMA_HOST

- `pytest tests/` deu **4 falhas** em test_pipeline. Diagnostico: sao testes de
  **integracao** (ja marcados `pytest.mark.integration`!) a correr em condicoes
  erradas — modo `local` persistido na BD + `OLLAMA_HOST=host.docker.internal`
  no `.env` (posto para o Docker), **inalcancavel a partir do venv** → ConnectTimeout.
- Fix de configuracao (mesmo padrao do QDRANT_HOST):
  - `.env` → `OLLAMA_HOST=http://localhost:11434` (correto para o venv);
  - [docker-compose.yml] `environment:` → `OLLAMA_HOST=http://host.docker.internal:11434`
    (ganha ao `.env` gracas ao `override=False`).
- Resultado: **unit 53/53** com `-m "not integration"`; **integracao 13/13** em
  modo online. Suite inteira saudavel; nada do trabalho novo partiu testes.

## 5. Corpus expandido para 14 documentos (pela Liane, via UI)

A Liane reconheceu que 1 documento era fraco para avaliacao ("fazer testes com
so um documento e um pouco mau nao?") e carregou pela UI de upload:

| Tipo | Conteudo |
|---|---|
| bula (12) | FI + RCM de 6 medicamentos: Ben-u-ron (paracetamol), Brufen (ibuprofeno), Clamoxyl (amoxicilina), Omeprazol, Varfine (varfarina), Ventilan (salbutamol) |
| guideline (2) | antibioterapia (16 chunks) + anticoagulacao (7 chunks) |

**141 chunks** no total. O `brufen_folheto.pdf` antigo foi **apagado pela
funcionalidade nova** (seccao 6) e substituido pelos Brufen_FI/RCM.

**Bateria de validacao do corpus (modo online):**
- PDF com nome nao-ASCII (`guideline_anticoagulação.pdf`) serve com HTTP 200 ✓
- Cruzada "Brufen + Varfine, ha interacao?" → AINE × varfarina, citando
  Varfine_FI ✓
- Filtrada `tipo_documento=guideline` → respondeu so da guideline
  (amoxicilina 500mg 8/8h na PAC) ✓
- Fora do corpus (insulina) → **recusou** com `contexto_suficiente=False`,
  explicando o que o corpus cobre ✓ (o "sabe dizer nao sei" — ouro para a defesa)

## 6. Funcionalidade nova: apagar documentos (RF de ciclo de vida)

Pergunta da Liane: "nao achas que devia dar para apagar documentos?"

- **Backend:** `DELETE /documentos/{tipo}/{nome}` ([main.py]) — so admin;
  mesmas defesas anti-traversal do GET /ficheiros; conta os chunks (count com
  filtro exact), apaga no Qdrant por **filtro de payload**
  (`ficheiro` + `tipo_documento`), apaga o PDF do disco, log com username,
  devolve `{chunks_removidos, pdf_removido}`; 404 se nada existe.
- **UI ([admin.js]):** botao "Apagar" no rodape de cada cartao; **modal de
  confirmacao em-app** (`confirmarModal` — substitui o window.confirm nativo a
  pedido da Liane; Promise<boolean>, Esc/clique-fora cancelam, foco no Cancelar,
  botao destrutivo vermelho); erro via barra de estado (sem alert()).
- **Testado ponta-a-ponta:** farmaceutico → 403; traversal `..%5C..` → 400;
  delete real → 12 chunks + PDF removidos; re-ingestao restaurou tudo.
- Nota conceptual (explicada a Liane): nao ha "tabela de documentos" — um
  documento e o conjunto de chunks com o mesmo metadata `ficheiro`; o nome do
  ficheiro funciona como ID dentro do tipo (simplificacao consciente).

## 7. Citacoes numeradas [n] (em vez de [Fonte: ficheiro, p.X])

Queixa da Liane: demasiadas fontes no corpo do texto. Decisao (apos discussao
de trade-offs): **estilo referencias academicas** — mantem a rastreabilidade
por afirmacao (argumento central do relatorio, RF08/RF13) sem o ruido.

- **prompt.py:** regra 2 reescrita — citar pelo NUMERO do excerto ([1], [1][3]),
  no fim da frase/paragrafo, sem repetir em frases consecutivas; PROMPT_GERACAO
  alinhado. **Disclaimer do template acentuado** (era a origem do AVISO sem
  acentos na UI — o LLM reproduzia-o verbatim) e frase de recusa idem.
- **pipeline.py:** o evento `meta` do stream passa a enviar fontes **numeradas
  pela ordem dos chunks, SEM deduplicar** — garantia 1:1 com os excertos [n]
  do prompt (o `_extrair_fontes` deduplicado podia desalinhar os numeros; o
  sync /consulta mantem o comportamento antigo).
- **chat.js:** tags de fontes ganham badge com o numero; marcas [n] no corpo
  viram sobrescrito discreto (`.cite-num`); CSS novo (.source-num).
- **Validado via /consulta/stream:** fontes numeradas 1-3 no meta; resposta com
  [1][2][3]; formato antigo ausente.

## 8. Polimento UX (varios pedidos da Liane ao longo da sessao)

| Mudanca | Detalhe |
|---|---|
| Label da categoria | Interno continua `bula`; UI mostra **"Bulas e RCM"** (filtro do chat) / **"Bula / RCM"** (upload e badges). Helper `rotuloTipo()` em api.js — decisao vinda de conversa dela no Claude.ai (rigor no relatorio: "FI e RCM") |
| Acentuacao | ~30 strings visiveis corrigidas: UI (tabs Definicoes→Definições/Historico→Histórico, vista Definicoes, auditoria, login/sessao, index.html, placeholders) + mensagens do backend (input_guard, disclaimer/NOTA do output_guard, avisos do generator) |
| Badge do header | "Operacional (12 pontos)" → so **"Operacional"** (nr de chunks no tooltip) — jargao fora do header; + "Sem ligação" acentuado |
| Stats fora da Consulta | Os 3 cartoes (documentos/chunks/tipos) removidos da tab Consulta (jargao, redundantes com a tab Documentos, empurravam o chat para baixo) |
| Conversa persistente | Trocar de tab e voltar ja NAO perde a conversa: snapshot do thread + mesmo sessionId restaurados pelo renderChat; "+ Nova conversa" limpa. Limites: F5 perde (estado em memoria); troca a meio de streaming pode nao mostrar essa resposta |
| PDFs abrem no viewer | `/ficheiros` passou a `Content-Disposition: inline` — abre no viewer do Chrome (download opcional a partir dele); o `#page=N` das citacoes passou a funcionar de facto |
| Toolbar dos documentos | Pesquisa por nome + filtro por tipo + ordenacao (Nome A-Z / Tipo / Mais chunks) + contador "X de Y" — client-side sobre cache local (`_docsCache`); estado vazio proprio |
| Cache-busting | `style.css?v=2` no index.html (o botao Apagar aparecia "nu" por cache do browser — o container ja servia o CSS novo) |
| Modal sem travessao | Texto do modal: "A ação é irreversível. O documento só volta com novo upload." (a pedido) |

## Ficheiros tocados (TUDO uncommitted no fim da sessao)

```
M  README.md                          <- qwen default + nota do modo local
M  docker-compose.yml                 <- + OLLAMA_HOST=host.docker.internal (env)
M  src/api/main.py                    <- DELETE /documentos/...; /ficheiros inline
M  src/api/static/index.html          <- acentos; style.css?v=2
M  src/api/static/js/admin.js         <- delete+modal; toolbar filtro/ordenacao; acentos; rotuloTipo
M  src/api/static/js/api.js           <- rotuloTipo(); acento na msg de sessao
M  src/api/static/js/chat.js          <- sem stats; conversa persistente; tags numeradas; cite-num; acentos
M  src/api/static/js/historico.js     <- acento
M  src/api/static/js/main.js          <- badge header; tabs acentuadas; acentos de sessao
M  src/api/static/style.css           <- delete-btn, modal, toolbar, citacoes (4 blocos novos)
M  src/config.py                      <- OLLAMA_MODEL=qwen2.5:3b-instruct (Parte 4 do C9)
M  src/guardrails/input_guard.py      <- prompt de dominio (marcas/fail-open); acentos
M  src/guardrails/output_guard.py     <- force_json; disclaimer/NOTA acentuados
M  src/llm_client.py                  <- force_json; num_ctx=8192; keep_alive=30m
M  src/query/crag.py                  <- force_json; truncagem local 1200
M  src/query/generator.py             <- avisos acentuados
M  src/query/pipeline.py              <- fontes numeradas no meta do stream
M  src/query/prompt.py                <- citacoes [n]; disclaimer/recusa acentuados
M  src/query/reformulator.py          <- migrado p/ chamar_llm (Parte 4 do C9)
M  src/query/reranker.py              <- envelope+parsing+truncagem (Parte 4 do C9)
D  data/documents/bulas/brufen_folheto.pdf      <- substituido
?? data/documents/bulas/*.pdf (12 novos) + guidelines/ (2)
?? docs/CONTEXTS/CONTEXT9.md, CONTEXT10.md
```

(+725/-198 linhas nos ficheiros de codigo; os PDFs do corpus sao versionados
no repo — o antigo estava tracked — por isso os 14 novos devem entrar no commit.)

## Validacoes feitas

- Guard de dominio: 5 casos em local (3 aceites, 2 rejeitados) + prova no container.
- Timing por etapa do modo local (355s; breakdown na seccao 3).
- Suite: unit 53/53 (`-m "not integration"`); integracao 13/13 (online).
- Delete: 403 / 400 traversal / delete real / re-ingestao de restauro.
- Corpus: 4 validacoes (nao-ASCII, cruzada, filtrada, fora-do-corpus).
- Citacoes numeradas: SSE end-to-end (meta numerado + [n] no texto, sem formato antigo).
- `/ficheiros`: `content-disposition: inline` confirmado (incl. filename utf-8).
- admin.js: `node --check` apos a toolbar (apanhou um catch orfao, corrigido).

**Nao corridos:**
- Clique manual em toda a UI nova num so passe (a Liane foi testando por partes).
- Cortes A/B/C do modo local (adiados por decisao dela).
- `test_auth.py` / `test_llm_client.py` (continuam por escrever).

## Pontos abertos / proximos passos

1. **COMMIT — critico.** ~21 ficheiros + 14 PDFs + 2 CONTEXTs so no working tree.
   Sugestao de commits tematicos: (a) viabilizacao+otimizacao modo local,
   (b) feature apagar documentos, (c) citacoes numeradas, (d) UX/acentos/labels,
   (e) corpus (PDFs), (f) docs (CONTEXTs). Ou um unico "preparacao para entrega".
   **Sem push** ate falar com o Ricardo (auto-deploy; producao em baixo).
2. **Avisar o Ricardo:** servidor em baixo (TCP 443) + force-push do `320a863`
   + (quando voltar) verificar login em prod (env vars do Coolify vs .env).
3. **Testes** `test_auth.py` + `test_llm_client.py` (auth e switch sem cobertura).
4. **Relatorio (Liane):** RF15; switch LLM com numeros medidos (355s breakdown,
   fidelidade 0.5-0.6 vs 0.97); ciclo de vida dos documentos (delete); corpus e
   bateria de validacao; citacoes numeradas como evolucao do RF08/RF13.
5. **Video** da apresentacao — sistema pronto; sugerida a demo da pergunta
   cruzada (Brufen+Varfine) e do "nao sei" (insulina).
6. Adiados: cortes A/B/C do local; persistencia da conversa a F5 (sessionStorage);
   singular/plural no cartao "1 TIPOS DE DOCUMENTO" (a Liane optou por nao mexer).

## Resumo executivo

- **Producao esta em baixo por infra** (TCP 443 sem resposta) — nao foi o deploy;
  assunto Ricardo. Apresentacao sera por video; prod nao sera mostrada.
- **Modo local ficou mais correto e marginalmente mais rapido** (num_ctx 8192
  corrige truncagem silenciosa; keep_alive; CRAG truncado) mas continua ~6 min
  em CPU — cortes maiores adiados; GPU e o unico salto real.
- **Guard de dominio** deixou de rejeitar marcas desconhecidas do modelo pequeno
  (fail-open em duvida).
- **Corpus real: 14 documentos / 141 chunks** (6 medicamentos FI+RCM + 2
  guidelines), carregado pela Liane na UI e validado com bateria de 4 testes —
  incluindo o "sabe dizer nao sei".
- **Apagar documentos** implementado (Qdrant delete por filtro + PDF + UI com
  modal proprio) e testado, fechando o ciclo de vida do corpus (governanca).
- **Citacoes numeradas [n] ↔ tags numeradas** — rastreabilidade por afirmacao
  mantida, ruido eliminado; numeracao garantida 1:1 com os excertos do prompt.
- **UX polida em ~10 frentes** (labels, acentos, badge, modal, toolbar, viewer
  inline, conversa persistente, chat sem jargao).
- **Suite de testes saudavel** (53 unit + 13 integracao) apos resolver o padrao
  de config do OLLAMA_HOST (.env=localhost; compose injeta host.docker.internal).
- **NADA committed** — e o ponto critico em aberto.
