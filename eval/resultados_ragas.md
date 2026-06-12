# Resultados da avaliacao RAGAS

- Data: 2026-06-12T00:18:22
- Pipeline em modo **online** (Claude); juiz: **claude-sonnet-4-6**; embeddings: Gemini (os do sistema)
- 11 perguntas do corpus + 1 de controlo (fora do corpus, excluida das medias)

## Medias (nucleo)

| Metrica | Media |
|---|---|
| faithfulness | **0.874** |
| answer_relevancy | **0.898** |
| llm_context_precision_with_reference | **1.0** |
| context_recall | **0.894** |

## Por pergunta

| id | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | suficiente | duracao (s) |
|---|---|---|---|---|---|---|
| q01_brufen_gi | 1.0 | 0.913 | 1.0 | 0.333 | True | 21.3 |
| q02_brufen_gravidez | 0.812 | 0.881 | 1.0 | 1.0 | True | 23.8 |
| q03_clamoxyl_indicacao | 0.952 | 0.923 | 1.0 | 1.0 | True | 20.8 |
| q04_varfine_interacoes | 0.933 | 0.993 | 1.0 | 1.0 | True | 34.8 |
| q05_omeprazol_indicacao | 0.714 | 0.925 | 1.0 | 1.0 | True | 21.6 |
| q06_ventilan_indicacao | 0.786 | 0.849 | 1.0 | 1.0 | True | 19.5 |
| q07_guideline_pac | 1.0 | 0.951 | 1.0 | 0.5 | True | 34.9 |
| q08_interacao_cruzada | 0.417 | 0.943 | 1.0 | 1.0 | True | 33.4 |
| q09_benuron_indicacao | 1.0 | 0.892 | 1.0 | 1.0 | True | 19.5 |
| q10_varfine_alimentos | 1.0 | 0.853 | 1.0 | 1.0 | True | 28.7 |
| q11_paracetamol_prolongado | 1.0 | 0.75 | 1.0 | 1.0 | True | 30.8 |
| q12_controlo_fora_corpus (controlo) | 0.462 | 0.0 | 0.0 | 1.0 | False | 38.6 |

> Nota metodologica: faithfulness e context precision/recall sao calculadas por LLM-juiz (claude-sonnet-4-6). O juiz partilha o modelo do gerador (auto-avaliacao parcial — limitacao reconhecida; as metricas sao ancoradas nos contextos recuperados e nas referencias, nao em opiniao livre do juiz). Answer relevancy usa os embeddings do sistema. As referencias foram redigidas a partir do texto dos documentos oficiais do corpus.