# CONTEXT11.md — Bateria de testes completa: unitarios, seguranca e avaliacao RAGAS

> Data: 2026-06-11/12. Cobre tudo desde o CONTEXT10: a sessao fechou os tres
> itens da "Semana 2" do plano de estagio — **testes unitarios** (53 → 130),
> **testes de seguranca** (sistematizados na suite) e **avaliacao com RAGAS**
> (12 perguntas, 4 metricas, resultados fortes). Inclui a decisao fundamentada
> de NAO correr o RAGAS em modo local no portatil, com o harness preparado
> para o fazer em infraestrutura adequada (trabalho futuro verificavel).

## Snapshot no fim do CONTEXT10

- A Liane fez **commit e push de tudo** (`64a28d6` — "troca de modelo local,
  adicao de mais documentos, com filtros e ordenacao...", 38 ficheiros,
  +1285/-198) para os DOIS remotes. O ponto critico "NADA committed" do
  CONTEXT10 ficou resolvido; o push ao `trabalho` re-disparara o deploy
  quando o servidor da Teclab voltar (continua em baixo — TCP 443 sem resposta).
- Sistema funcional completo: corpus 14 docs/141 chunks, apagar documentos,
  citacoes numeradas, UX polida. Suite na altura: 53 unit + 13 integracao.
- Em falta da Semana 2: testes de auth/switch, seguranca sistematica, RAGAS.

---

## 1. Testes unitarios novos: 53 → 130 (todos hermeticos, ~30s)

### 1.1 Infraestrutura ([tests/conftest.py], NOVO)

- `bd_temporaria` — redireciona a BD de auth para SQLite temporario
  (monkeypatch de `src.auth.db.AUTH_DB_PATH`) + segredo JWT fixo de teste:
  os testes **nunca tocam na data/auth.db real** nem dependem do `.env`.
- `cliente_api` — TestClient da FastAPI **sem lifespan** (o seed real nunca
  corre); cria `admin_teste`/`farm_teste` diretamente na BD temporaria.
- Helper `obter_token()` para login nos testes de API.

### 1.2 Novos ficheiros de teste

| Ficheiro | Testes | Cobre |
|---|---|---|
| [tests/test_llm_client.py] | 12 | Switch online/local: persistencia SQLite, round-trip, valores invalidos/corrompidos→default, `chamar_llm`/`stream_llm` com AMBOS os providers mockados, `force_json` liga format=json so no Ollama, modo relido a cada chamada |
| [tests/test_auth.py] | 27 | bcrypt (hash nunca em claro, salt aleatorio), JWT (round-trip, expirado, assinatura forjada, malformado, papel invalido), login 200/401, gating, traversal, upload |
| [tests/test_reranker.py] | 13 | TODAS as ramificacoes de parsing que ja falharam em modo local (envelope, array, objeto unico, fence markdown, JSON truncado, dict alienigena), clamp de scores alucinados, indices fora do intervalo, truncagem 700 local vs 4000 online, force_json |
| [tests/test_crag.py] | 11 | Parsing da avaliacao + fallback conservador, truncagem 1200 em local, e os 5 caminhos do crag_pipeline (suficiente a 1a / sem retry / reformulacao resolve / melhora abaixo do threshold / piora→mantem originais) |
| [tests/test_reformulator.py] | 5 | Early-return sem historico (nao paga LLM), dicts E objetos, defesas contra output vazio/gigante |
| [tests/test_generator.py] | 9 | Resposta padrao sem chunks, dedupe de fontes, NOTA do CRAG (sync e streaming), numeracao [n] dos excertos no prompt |

Racional dos numeros (pergunta da Liane "130 nao e demais?"): **um teste = um
comportamento/ramificacao**; os 5 testes do descodificar_token sao 5 vetores de
ataque distintos; os 13 do reranker correspondem a formatos de output que
aconteceram MESMO com o qwen. Suite inteira corre em ~30s, sem rede.

### 1.3 Licao de engenharia: testes nao podem depender do corpus vivo

Ao correr a suite completa, `test_loader`/`test_chunker` rebentaram: apontavam
ao `brufen_folheto.pdf` — **apagado pela propria Liane** com a funcionalidade
nova de delete (corpus e gerido pelo admin na UI). Fix estrutural: fixture
propria **[tests/fixtures/documents/bulas/bula_exemplo.pdf]** (PDF sintetico
de 3 paginas gerado por codigo, ~8K chars extraiveis) e os dois ficheiros
migrados para ela. Os testes ficaram imunes a gestao de documentos — boa
historia para o relatorio.

## 2. Testes de seguranca (sistematizados na suite)

Distincao explicada a Liane (util para o relatorio): *unitario* descreve o
AMBITO (uma peca isolada, mocks); *de seguranca* descreve o PROPOSITO (resistir
a uso malicioso — o "sucesso" e uma rejeicao). Na nossa suite, os testes de
seguranca sao implementados como unitarios/API. Frase-sintese:
**"os unitarios verificam o que o sistema faz; os de seguranca verificam o que
o sistema nao deixa fazer."**

Cobertura: 401 sem token/adulterado; **403** de farmaceutico em rotas de admin
(/audit, /admin/llm-mode, DELETE /documentos, /upload); token via ?token= no
/ficheiros; **path traversal nas duas rotas de ficheiros** — com a descoberta
de defesa em camadas: `..%5C` e rejeitado pela NOSSA validacao (400), `..%2F`
nem chega ao handler (o router do Starlette nao deixa um path param atravessar
segmentos → 404). Upload: tipo invalido e nao-PDF → 400. Prompt injection ja
estava coberto (regex do input_guard).

## 3. Avaliacao RAGAS (o item grande)

### 3.1 Setup e obstaculos (todos documentados no proprio script)

Instalado `ragas` 0.4.3 + `langchain-anthropic` (a stack ja era LangChain 1.x;
o projeto continuou a funcionar — verificado com a suite). Quatro obstaculos
reais, por ordem:

| # | Obstaculo | Solucao |
|---|---|---|
| 1 | ragas 0.4.3 importa modulos legacy removidos do langchain-community 0.4.x (`chat_models.vertexai`) | **Shim** no script de avaliacao: stubs em sys.modules (usados so em isinstance de modelos Vertex que nao usamos) |
| 2 | O `evaluate()` do ragas **ignorava os nossos embeddings** e usava um default com outra dimensionalidade → answer_relevancy rebentava com shapes (3,1024) vs (3072,1) | Metricas chamadas **diretamente** (`single_turn_ascore`) com llm/embeddings explicitos por metrica |
| 3 | **Bug do provider**: `langchain-google-genai` 4.2.2 `embed_documents` com N textos devolve UM unico vetor (3×1024 concatenados = o 3072 do reshape!). Diagnostico fechado com lote de 3 → `[3072]`. O embedder do SISTEMA ja sobrevivia a isto sem sabermos: o `gerar_embeddings` valida `len(vetores) != len(lote)` e cai para individual | Wrapper `_EmbeddingsPorTexto` na avaliacao: lotes de 1 texto |
| 4 | Juiz Gemini 2.5 Flash: a chave Google e **free-tier — 20 pedidos/DIA** no generativo (429 RESOURCE_EXHAUSTED com retries silenciosos que pareciam hang). Os embeddings tem quota propria (folgada) — por isso indexacao/retrieval sempre funcionaram | Juiz voltou ao **Claude** (creditos repostos) + timeout de 240s por metrica (nunca mais pendura em silencio) |

Nota operacional: a meio da sessao os **creditos da API Anthropic esgotaram**
(bloqueou pipeline online + juiz); a Liane carregou e confirmou-se com chamada
minima. O Docker Desktop tambem esteve desligado num momento (a Liane gere o
arranque) — o script ganhou mensagem clara em vez de stack trace.

### 3.2 Dataset ([eval/dataset_avaliacao.json])

**12 perguntas: 11 do corpus + 1 de controlo** (insulina, fora do corpus, para
medir a recusa honesta; excluida das medias). As referencias foram redigidas
**a partir do texto real dos PDFs** (extraido com o loader e verificado por
pesquisa de termos-chave — ex.: "amoxicilina, 500mg, 8/8 horas" na guideline,
"produtos de arando" no Varfine_FI). Inclui pergunta cruzada (ibuprofeno+
varfarina) e perguntas de guideline.

### 3.3 Runner ([eval/avaliar_ragas.py])

`python eval/avaliar_ragas.py [--modo online|local] [--limite N] [--so-metricas]`
- Corre `consultar()` no modo pedido (define e restaura o llm_mode), guarda
  **cache de respostas** (re-julgar nao re-paga o pipeline), julga com as 4
  metricas (Faithfulness, AnswerRelevancy, LLMContextPrecisionWithReference,
  LLMContextRecall) e escreve `resultados_ragas.{json,md}` com medias do
  nucleo, tabela por pergunta e nota metodologica.
- Juiz: claude-sonnet-4-6, **constante entre modos** (comparabilidade);
  auto-avaliacao parcial no braco online reconhecida na nota (a existir vies,
  favorece o online — nao inventa o fosso para o local).

### 3.4 Resultados (modo online, 11 perguntas do nucleo)

| Metrica | Media | Leitura |
|---|---|---|
| context_precision | **1.00** | retrieval+reranker entregam contexto 100% util |
| answer_relevancy | **0.898** | respostas focadas na pergunta |
| context_recall | **0.894** | contexto cobre quase tudo o que a referencia exige |
| faithfulness | **0.874** | afirmacoes ancoradas nos documentos |

Casos com historia (para a analise do relatorio):
- **q12 controlo (insulina)**: answer_relevancy **0.0** e precision **0.0** —
  aqui e o resultado DESEJADO: o sistema recusou (suficiente=False) em vez de
  alucinar; prova quantitativa do "sabe dizer nao sei".
- **q08 cruzada (0.42 de faithfulness)**: a resposta encadeia
  Brufen→ibuprofeno→AINE→interacao com varfarina; parte do encadeamento e
  inferencia farmacologica nao literal nos excertos — o juiz penaliza
  inferencia (rigor, nao erro clinico).
- **q01 recall 0.33**: a referencia lista mais efeitos GI do que os 3 chunks
  do RERANK_TOP_N=3 cobrem — trade-off precisao/cobertura documentavel.

### 3.5 Decisao: RAGAS do modo local NAO corre no portatil

Decisao da Liane, com fundamentacao trabalhada em conjunto:
- ~6 min/consulta em CPU (medido) × 12 = ~80 min com o portatil (Ryzen 5625U,
  7.4 GB RAM) a segurar Docker+Qdrant+Ollama em simultaneo → os resultados
  mediriam **a contencao de recursos do portatil**, nao o modo local.
- O modo local ja tem dados quantitativos citaveis: breakdown 355s/etapa,
  fidelidade do output_guard ~0.5-0.6 vs 0.97-1.0 online.
- Formulacao para o relatorio: avaliacao A/B em infraestrutura com GPU fica
  como **trabalho futuro** — e com a flag `--modo local` implementada e
  testada (sintaxe/help/ficheiros separados), a frase *"o harness de avaliacao
  suporta ambos os modos; a execucao fica como trabalho futuro em
  infraestrutura adequada"* e **verdade verificavel, nao promessa**.

## Ficheiros (uncommitted no fim da sessao)

```
?? tests/conftest.py                  <- fixtures hermeticas (BD temp, cliente API)
?? tests/test_llm_client.py           <- 12 testes do switch
?? tests/test_auth.py                 <- 27 testes auth/seguranca/upload
?? tests/test_reranker.py             <- 13 testes de parsing/truncagem
?? tests/test_crag.py                 <- 11 testes CRAG
?? tests/test_reformulator.py         <- 5 testes
?? tests/test_generator.py            <- 9 testes
?? tests/fixtures/                    <- bula_exemplo.pdf (PDF sintetico)
M  tests/test_loader.py               <- migrado para a fixture
M  tests/test_chunker.py              <- migrado para a fixture
?? eval/                              <- dataset, avaliar_ragas.py, resultados_ragas.{json,md},
                                         cache_respostas.json, run_*.log (logs: apagar ou ignorar)
?? docs/CONTEXTS/CONTEXT11.md
```

## Validacoes feitas

- Suite completa: **130 passed** (unit, ~30s) + 13 integracao (a parte).
- RAGAS ponta-a-ponta: 12 perguntas pelo pipeline online (~5,5 min) + 48
  julgamentos; as 4 metricas calculam (incluindo answer_relevancy apos o fix
  do bug de batch do provider).
- `--modo local`: sintaxe, --help, caminhos separados; resultados online
  confirmados intactos apos o refactor.
- Creditos Anthropic confirmados repostos com chamada minima.

**Nao corridos:**
- RAGAS em modo local (decisao fundamentada — seccao 3.5).
- O bug de batch do langchain-google-genai no embedder do SISTEMA continua
  contornado pelo fallback individual (funciona, mas cada lote falha primeiro
  → ingestao mais lenta do que podia; ver pontos abertos).

## Pontos abertos / proximos passos

1. **Commit** dos testes + eval/ (a Liane committa; excluir/apagar eval/run_*.log).
2. **requirements**: `ragas` e `langchain-anthropic` foram instalados mas NAO
   estao no requirements.txt — decidir: acrescentar, ou criar
   `requirements-eval.txt` separado (sao dependencias so de avaliacao).
3. **Relatorio (Liane)** — material todo pronto: metricas RAGAS + tabela por
   pergunta (eval/resultados_ragas.md), breakdown de latencia local, trade-offs
   do switch, justificacao da secao 3.5, distincao unitarios/seguranca.
4. **Ricardo**: servidor em baixo (TCP 443) + force-push antigo + (quando
   voltar) validar login em prod; especificacoes do servidor se a avaliacao
   local em GPU interessar.
5. **Video** da apresentacao.
6. (Opcional) Investigar/atualizar o `langchain-google-genai` quando houver
   versao com o batch corrigido — a ingestao deixa de pagar o fallback.

## Resumo executivo

- **Semana 2 do plano de estagio: fechada.** Unitarios 53→**130** (hermeticos,
  ~30s), seguranca sistematizada (gating, JWT, traversal em camadas, upload),
  e **RAGAS executado**: faithfulness 0.874, answer_relevancy 0.898,
  context_precision 1.0, context_recall 0.894 (11 perguntas; controlo provou
  a recusa honesta com relevancy 0.0).
- **Quatro bugs/armadilhas de dependencias vencidos** no caminho do RAGAS
  (legacy imports do ragas, evaluate() a ignorar embeddings, batch do provider
  Google a devolver 1 vetor para N textos — que o embedder do sistema ja
  contornava sem sabermos —, e quota free-tier do Gemini), todos documentados
  no proprio script.
- **RAGAS do modo local adiado com fundamento** (CPU do portatil mediria
  contencao, nao qualidade) e com instrumento pronto: `--modo local`
  implementado — trabalho futuro verificavel.
- Testes deixaram de depender do corpus gerido pelo admin (fixture propria).
- Por fazer: commit (Liane), decisao do requirements de avaliacao, relatorio,
  video, conversas com o Ricardo.
