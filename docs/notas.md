# Notas — Comandos do Projeto RAG Farmaceutico

## Iniciar o ambiente (fazer sempre que abrir o projeto)

```bash
# 1. Ativar o ambiente virtual
venv\Scripts\activate

# 2. Abrir o Docker Desktop (manualmente)

# 3. Iniciar o container Qdrant
docker start qdrant

# 4. Iniciar a API
uvicorn src.api.main:app --reload --port 8000

# 5. Abrir programa
http://localhost:8000/
```

## Pipeline de ingestao (indexar documentos no Qdrant)

```bash
# Ingerir todos os PDFs das subpastas (bulas/, monografias/, etc.)
python -m src.ingestion.pipeline --pasta data/documents

# Ingerir um ficheiro especifico
python -m src.ingestion.pipeline --ficheiro data/documents/bulas/nome.pdf --tipo bula
```

## Pipeline de consulta (fazer perguntas)

```bash
# Pergunta simples
python -m src.query.pipeline "Quais sao os efeitos secundarios do ibuprofeno?"

# Filtrar por tipo de documento
python -m src.query.pipeline "Qual a posologia do brufen?" --tipo bula
python -m src.query.pipeline "Qual a posologia do brufen?" --tipo monografia
```

## Testes

```bash
# Correr todos os testes
python -m pytest tests/ -v

# Apenas testes unitarios (sem precisar de APIs)
python -m pytest tests/test_loader.py tests/test_chunker.py tests/test_indexer.py tests/test_input_guard.py tests/test_output_guard.py -v

# Apenas testes de integracao (precisa de Qdrant + API keys)
python -m pytest tests/test_retriever.py tests/test_pipeline.py -v

# Gerar relatorio HTML
python -m pytest tests/ -v --html=tests/reports/report.html --self-contained-html
```

## Qdrant

```bash
# Ver se o container esta a correr
docker ps

# Parar o Qdrant
docker stop qdrant

# Dashboard do Qdrant (abrir no browser)
# http://localhost:6333/dashboard
```

Se estiveres a usar Docker Compose, não precisas de iniciar o Qdrant manualmente.
O comando recomendado é:

```bash
docker compose up --build -d
```

## API (FastAPI)

```bash
# Iniciar a API
uvicorn src.api.main:app --reload --port 8000

# Swagger UI (abrir no browser)
# http://localhost:8000/docs

# Endpoints disponiveis:
# POST /consulta    — fazer uma pergunta
# POST /ingestao    — re-ingerir documentos
# GET  /health      — estado do sistema
# GET  /audit       — ver logs de auditoria
```

## Docker Compose (deployment)

```bash
# Construir e iniciar tudo (Qdrant + API) com um so comando
docker compose up --build

# Em background
docker compose up --build -d

# Ver logs
docker compose logs -f api
docker compose logs -f qdrant

# Parar tudo
docker compose down

# Parar e apagar volumes (CUIDADO: apaga dados do Qdrant)
docker compose down -v

sempre que quiser alterar atualizar o site no localhost mesmo fazer isto:
docker compose down
docker compose up --build
```

Depois de `docker compose up`, a API fica disponivel em:

- Interface: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Qdrant dashboard: http://localhost:6333/dashboard

> Nota: ao usar Docker Compose, o Qdrant corre dentro do Docker (nao precisa de iniciar manualmente).
> O volume `qdrant_data` persiste os dados entre reinicializacoes.

## Instalar dependencias (so se necessario)

```bash
pip install -r requirements.txt
```

## Estrutura das pastas de documentos

```
data/documents/
├── bulas/            -> PDFs de folhetos informativos
├── monografias/      -> PDFs de monografias/RCM
├── guidelines/       -> PDFs de guidelines
└── normas/           -> PDFs de normas INFARMED
```

Para adicionar um novo documento: colocar o PDF na subpasta correta e correr o pipeline de ingestao.
