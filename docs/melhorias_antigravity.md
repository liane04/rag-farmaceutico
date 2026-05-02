# 🔧 Melhorias Identificadas — RAG Farmacêutico

Análise feita pelo Antigravity a 02/05/2026.

---

## 🔴 Prioridade Alta

### 1. `payload.pop("texto")` destrutivo no retriever
**Ficheiro:** `src/query/retriever.py`, linha 110

O `.pop("texto")` remove a chave do payload original do Qdrant. Se o payload for reutilizado (ex: caching), o `texto` já não existe.

**Correção:** Mudar para `.get("texto")` e construir metadados explicitamente:
```python
texto = payload.get("texto")
metadados = {k: v for k, v in payload.items() if k != "texto"}
```

### 2. Limpar o README
**Ficheiro:** `README.md`

O README tem notas pessoais misturadas com a documentação ("para iniciar cada vez que fecho:"). Mover essas notas para um ficheiro separado (ex: `NOTAS_PESSOAIS.md`) e adicionar:
- Diagrama de arquitetura
- Descrição dos endpoints da API
- Estrutura do projeto

---

## 🟡 Prioridade Média

### 3. Reranker muta o chunk original
**Ficheiro:** `src/query/reranker.py`, linha 92

```python
chunk.score = avaliacao.get("score", 0) / 10.0  # muta o objeto original!
```

**Correção:** Criar novos objetos `ChunkRecuperado` em vez de mutar os originais.

### 4. Clientes API criados repetidamente
**Ficheiros:** Vários (`crag.py`, `reranker.py`, `generator.py`, `output_guard.py`)

Cada chamada ao LLM cria um `Anthropic(api_key=...)` novo. Usar singleton ou FastAPI `Depends()`.

### 5. Adicionar mocks nos testes de integração
**Ficheiros:** `tests/test_pipeline.py`, `tests/test_retriever.py`

Os testes requerem Qdrant + APIs externas. Adicionar mocks para correr em CI/CD sem consumir tokens.

### 6. Tokenização esparsa muito básica
**Ficheiro:** `src/ingestion/indexer.py`, função `_texto_para_sparse()`

A tokenização por `.split()` não lida com pontuação, stopwords nem normalização. Considerar `rank_bm25` ou pelo menos `nltk.word_tokenize` com stopwords em português.

---

## 🟢 Prioridade Baixa (Nice-to-have)

### 7. Substituir `print()` por logging estruturado
Usar `logging` do Python em vez de `print()` em todo o projeto. Permite controlar níveis (DEBUG, INFO, WARNING) e redirecionar para ficheiros.

### 8. Rate limiting na API
Adicionar rate limiting no FastAPI para proteger contra abuso (ex: `slowapi`).

### 9. Cache de embeddings de queries frequentes
Queries repetidas geram embeddings idênticos — cachear com um decorator simples.

### 10. Versionamento de modelos
Registar versões dos modelos usados (Gemini, Claude) nos logs de auditoria para reprodutibilidade.

---

## ✅ O que já está bem (não mexer)

- Arquitetura modular (ingestão/consulta/guardrails separados)
- Recuperação híbrida com RRF no Qdrant
- CRAG com reformulação automática
- Guardrails de input (3 camadas) e output (fidelidade + disclaimer)
- Docstrings e type hints consistentes
- IDs determinísticos (uuid5) na indexação
- Docker Compose funcional
- Suite de testes (7 ficheiros)
