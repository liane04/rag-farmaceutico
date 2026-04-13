# Sistema RAG para Suporte à Decisão Farmacêutica

Sistema baseado em Retrieval-Augmented Generation (RAG) para apoio à decisão em contexto farmacêutico, desenvolvido como projeto final de licenciatura em Engenharia Informática na UTAD.

## Descrição

O sistema permite carregar documentação farmacêutica oficial portuguesa (bulas, monografias, guidelines, normas INFARMED) e responder a questões clínicas em linguagem natural, com citação explícita das fontes utilizadas.

**Stack tecnológica:** LangChain · Gemini Embedding 2 · Claude 3.5 Sonnet · Qdrant · FastAPI · Docker

## Pré-requisitos

- Python 3.12 ou 3.13 (3.14+ não é suportado — incompatível com Pydantic V1 usado pelo LangChain)
- Docker Desktop
- Git
- Chave de API Google (Gemini Embedding 2)
- Chave de API Anthropic (Claude 3.5 Sonnet)

## Instalação

**1. Clonar o repositório**

```bash
git clone https://github.com/liane04/rag-farmaceutico.git
cd rag-farmaceutico
```

**2. Criar e ativar o ambiente virtual**

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac
```

**3. Instalar dependências**

```bash
pip install -r requirements.txt
```

**4. Configurar variáveis de ambiente**

Cria um ficheiro `.env` na raiz do projeto com o seguinte conteúdo:

GOOGLE_API_KEY=a_tua_chave_aqui
ANTHROPIC_API_KEY=a_tua_chave_aqui
QDRANT_HOST=localhost
QDRANT_PORT=6333

**5. Levantar o Qdrant**

```bash
docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

O dashboard do Qdrant fica disponível em http://localhost:6333/dashboard

Se preferires correr a API também em Docker, usa o `docker compose up --build` na raiz do projeto.
Nesse modo, a API já fica configurada para falar com o Qdrant através do porto publicado no host.

## Autora

Liane Duarte — al79012 — UTAD 2025/2026

**Orientadores:** Ricardo Costa (Teclab) · Paulo Oliveira · Eduardo Pires (UTAD)

para iniciar cada vez que fecho:

1. `venv\Scripts\activate`
2. abrir Docker Desktop
3. se estiveres a correr tudo manualmente:
   - `docker start qdrant`
4. se estiveres a usar Docker Compose:
   - `docker compose up --build -d`

   para correr os testes:

   python -m pytest tests/test_retriever.py tests/test_pipeline.py -v
