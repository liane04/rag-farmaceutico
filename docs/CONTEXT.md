# CONTEXT.md — Sistema RAG para Suporte à Decisão Farmacêutica

## Identificação

- **Autora:** Liane Duarte — al79012
- **Curso:** Licenciatura em Engenharia Informática — UTAD 2025/2026
- **Unidade curricular:** Laboratório de Projeto em Engenharia Informática
- **Orientadores:** Ricardo Costa (Teclab) · Paulo Oliveira · Eduardo Pires (UTAD)
- **Contexto:** Projeto final de licenciatura + estágio na Teclab (projetos paralelos mas distintos)

---

## Descrição do Projeto

Sistema baseado em Retrieval-Augmented Generation (RAG) para suporte à decisão farmacêutica em português, construído sobre documentação farmacêutica oficial portuguesa (bulas, monografias, guidelines, normas INFARMED). O sistema responde a questões clínicas em linguagem natural com citação explícita das fontes.

---

## Stack Tecnológica (decisões finais)

| Componente                  | Tecnologia                    | Motivo                                                                       |
| --------------------------- | ----------------------------- | ---------------------------------------------------------------------------- |
| Framework de orquestração | LangChain                     | Maturidade, modularidade, suporte nativo à stack                            |
| Modelo de embedding         | Gemini Embedding 2 (Google)   | Suporte nativo a PDFs, +100 línguas incluindo português                    |
| Modelo generativo           | Claude 3.5 Sonnet (Anthropic) | Menor taxa de alucinações, maior fidelidade ao contexto                    |
| Base de dados vetorial      | Qdrant                        | Recuperação híbrida, filtragem por metadados, deployment local via Docker |
| API                         | FastAPI                       | Performance, validação automática, Swagger UI                             |
| Deployment                  | Docker                        | Reprodutibilidade, conformidade RGPD (deployment local)                      |
| Extração de texto PDF     | PyMuPDF                       | Texto corrido                                                                |
| Extração de tabelas PDF   | pdfplumber                    | Preserva estrutura tabular                                                   |

---

## Arquitetura (decisão final)

Combinação de **Advanced RAG + Modular RAG + CRAG**.

Arquiteturas rejeitadas e razões:

- **Naive RAG** — sem recuperação híbrida nem guardrails
- **GraphRAG** — complexidade de construção do grafo fora do âmbito
- **Agentic RAG** — imprevisibilidade incompatível com EU AI Act (alto risco)
- **Self-RAG** — exige fine-tuning do modelo generativo

---

## Arquitetura do Sistema — 3 camadas

1. **Camada de entrada e controlo** — API REST (FastAPI) + guardrails de input/output
2. **Camada de orquestração** — pipeline RAG (LangChain)
3. **Base de conhecimento** — corpus documental indexado no Qdrant

---

## Pipeline de Ingestão

1. Extração de texto corrido (PyMuPDF) e tabelas (pdfplumber)
2. Limpeza e normalização (remoção de cabeçalhos/rodapés, normalização de espaços)
3. Chunking — 1000 tokens, overlap 200 tokens (configurável)
4. Associação de metadados (tipo de documento, ficheiro, data, página, secção)
5. Geração de embeddings (Gemini Embedding 2)
6. Indexação no Qdrant (vetor + metadados)

---

## Pipeline de Consulta

1. Guardrail de input (validação de domínio + deteção de prompt injection)
2. Geração de embedding da query (Gemini Embedding 2)
3. Recuperação híbrida no Qdrant (semântica + keyword, top 10)
4. Reranking com LLM-as-Judge (Claude 3.5 Sonnet, seleciona top 3)
5. Avaliação de relevância CRAG (se insuficiente → reformula query → nova recuperação)
6. Geração de resposta com citação de fontes (Claude 3.5 Sonnet)
7. Guardrail de output (fidelidade + disclaimer obrigatório)
8. Registo de auditoria (query, chunks, resposta, timestamp, utilizador)

---

## Guardrails

- **Input** — validação de domínio farmacêutico + deteção de prompt injection (RF05)
- **Contexto** — avaliação de relevância CRAG, reformulação de query, recusa se insuficiente (RF06, RF07)
- **Output** — verificação de fidelidade + disclaimer obrigatório (RF13, RF14)
- **Auditoria** — registo imutável de todas as interações (RF09, Artigo 12.º EU AI Act)

---

## Requisitos (resumo)

**Funcionais:** RF01 a RF14 (ingestão, indexação, recuperação híbrida, geração fundamentada, validação de input/output, controlo de acesso, auditoria, interface, gestão de documentos, filtragem por tipo, transparência)

**Não funcionais:** RNF01 a RNF10 (desempenho ≤10s, fiabilidade, rastreabilidade, privacidade RGPD, segurança, manutenibilidade, portabilidade Docker, usabilidade, conformidade EU AI Act, encriptação)

---

## Enquadramento Regulatório

- **RGPD** — dados de saúde como categoria especial, privacy by design e by default
- **EU AI Act** — sistema de alto risco (Artigos 9, 13, 14, 17), transparência e supervisão humana
- **INFARMED** — fonte de documentação oficial + boas práticas farmacêuticas (responsabilidade clínica do farmacêutico)

---

## Estado do Relatório

| Capítulo                                 | Estado                                                                                          |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Cap. 1 — Introdução                    | ✅ Completo (versão revista do 1.1 pendente de substituição)                                 |
| Cap. 2 — Enquadramento Teórico          | ✅ Completo (faltam citações Self-RAG e CRAG em 2.2.2; corrigir definição cosseno em 2.3.2) |
| Cap. 3 — Estado da Arte                  | ✅ Completo                                                                                     |
| Cap. 4.1 — Requisitos                    | ✅ Completo                                                                                     |
| Cap. 4.2 — Arquitetura                   | ✅ Completo (Tabela 5 a expandir com critérios explícitos)                                    |
| Cap. 4.3.1 — Stack tecnológica          | ✅ Completo (atualizar para Gemini Embedding 2)                                                 |
| Cap. 4.3.2 — Processamento e indexação | ❌ Por escrever (após implementação)                                                         |
| Cap. 4.3.3 — Recuperação e geração   | ❌ Por escrever (após implementação)                                                         |
| Cap. 4.3.4 — Interface e deployment      | ❌ Por escrever (após implementação, incluir Coolify)                                        |
| Cap. 5 — Avaliação e Resultados        | ❌ Por escrever (após implementação e testes RAGAS)                                          |
| Cap. 6 — Conclusão                      | ❌ Por escrever                                                                                 |

---

## Estado da Implementação

| Fase                                | Estado       |
| ----------------------------------- | ------------ |
| Fase 1 — Ambiente e infraestrutura | ✅ Completo  |
| Fase 2 — Pipeline de ingestão     | 🔄 Em curso  |
| Fase 3 — Pipeline de consulta      | ❌ Por fazer |
| Fase 4 — API e interface           | ❌ Por fazer |

**Ambiente:** Windows, VS Code, Python 3.14.3, venv, Docker Desktop 29.3.1, Qdrant a correr em localhost:6333

**Repositório:** https://github.com/liane04/rag-farmaceutico

---

## Jira — Épicos e Tarefas relevantes

- **EP0** — Deliverables UC (pitch 7 abril, poster, apresentação)
- **T3.1** — Análise comparativa arquitetura RAG ✅
- **T3.2** — Design do sistema ✅
- **T3.3 e seguintes** — Implementação (em curso)

---

## Notas importantes

- O projeto é **inteiramente individual** (não confundir com o trabalho de equipa do estágio na Teclab)
- Na Teclab os colegas usam LangChain, from-scratch e LlamaIndex em paralelo — o projeto da Liane usa LangChain
- O Gemini Embedding 2 substituiu o text-embedding-3-small (OpenAI) — atualizar Figuras 7, 8 e 9 no draw.io
- Deployment final previsto via **Coolify** (a documentar em 4.3.4)
- Avaliação do sistema com framework **RAGAS**
