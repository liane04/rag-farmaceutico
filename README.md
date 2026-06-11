# Sistema RAG para Suporte à Decisão Farmacêutica

Sistema baseado em Retrieval-Augmented Generation (RAG) para apoio à decisão em contexto farmacêutico, desenvolvido como projeto final de licenciatura em Engenharia Informática na UTAD.

## Descrição

O sistema permite carregar documentação farmacêutica oficial portuguesa (bulas, monografias, guidelines, normas INFARMED) e responder a questões clínicas em linguagem natural, com citação explícita das fontes utilizadas. O acesso é protegido por autenticação, com dois perfis de utilizador (farmacêutico e administrador).

**Stack tecnológica:** LangChain · Gemini Embedding 2 (embeddings) · Claude Sonnet 4.6 / Ollama (geração) · Qdrant · FastAPI · SQLite · Docker

## Funcionalidades

- **Consulta conversacional** com resposta em *streaming* e citação das fontes (abre o PDF na página citada).
- **Pipeline RAG** com reranking (LLM-as-Judge), auto-correção (CRAG) e verificação de fidelidade da resposta.
- **Autenticação JWT** com dois perfis: `farmaceutico` (consulta + histórico) e `admin` (+ upload, ingestão, auditoria, definições).
- **Modo de geração comutável** pelo admin: `online` (Claude — qualidade máxima) ou `local` (Ollama — os dados ficam no servidor).
- **Auditoria** de todas as consultas, por utilizador.

## Pré-requisitos

- Python 3.12 ou 3.13 (3.14+ não é suportado — incompatível com Pydantic V1 usado pelo LangChain)
- Docker Desktop
- Git
- Chave de API Google (Gemini Embedding 2)
- Chave de API Anthropic (Claude Sonnet 4.6) — para o modo `online`
- *(Opcional)* [Ollama](https://ollama.com) com um modelo puxado — para o modo `local`

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

Cria um ficheiro `.env` na raiz do projeto (vê também `.env.example`):

```
# --- APIs ---
GOOGLE_API_KEY=a_tua_chave_google
ANTHROPIC_API_KEY=a_tua_chave_anthropic

# --- Qdrant ---
QDRANT_HOST=localhost
QDRANT_PORT=6333

# --- Autenticação ---
# Gerar com: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=chave_secreta_longa_e_aleatoria

# Passwords das contas iniciais (obrigatório)
SEED_ADMIN_PASSWORD=...
SEED_FARMACEUTICO_PASSWORD=...

# --- (Opcional) LLM local via Ollama ---
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b-instruct
LLM_MODE_DEFAULT=online
```

**5. Levantar o Qdrant**

```bash
docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

O dashboard do Qdrant fica disponível em http://localhost:6333/dashboard

## Arranque

**Opção A — API local, Qdrant em Docker:**

```bash
docker start qdrant
venv\Scripts\activate
uvicorn src.api.main:app --reload --port 8000
```

**Opção B — tudo em Docker:**

```bash
docker compose up --build -d
```

A aplicação fica disponível em **http://localhost:8000**.

### Contas de utilizador

As contas `admin` e `farmaceutico` são criadas automaticamente no arranque, com as passwords definidas no `.env` (`SEED_ADMIN_PASSWORD` / `SEED_FARMACEUTICO_PASSWORD`). Para as (re)semear manualmente:

```bash
python -m src.auth.seed
```

## Ingestão de documentos

Coloca os PDFs em `data/documents/{bulas,monografias,guidelines,normas}/` (a subpasta determina o tipo de documento) e corre:

```bash
python -m src.ingestion.pipeline --pasta data/documents
# ou um ficheiro específico:
python -m src.ingestion.pipeline --ficheiro data/documents/bulas/brufen.pdf --tipo bula
```

Em alternativa, faz *upload* pela interface (perfil admin).

## Utilização pela linha de comandos

```bash
python -m src.query.pipeline "Quais são os efeitos secundários do ibuprofeno?"
python -m src.query.pipeline "..." --tipo bula
```

## Modo de geração (online / local)

Por defeito o sistema usa **Claude** (`online`). O administrador pode alternar para **Ollama** (`local`) na aba *Definições* da interface, ou via API:

```bash
# requer token de admin
curl -X POST http://localhost:8000/admin/llm-mode \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"modo":"local"}'
```

> **Nota:** o modo `local` requer o Ollama a correr. O default `qwen2.5:3b-instruct` corre em CPU e completa o pipeline inteiro (usa `format=json` nos passos estruturados — reranker/CRAG/fidelidade), mas a fidelidade fica abaixo da do Claude. Para qualidade máxima usa o modo `online`, ou um modelo local maior (≥ 7-8B, idealmente com GPU). Modelos muito pequenos (ex.: `llama3.2:1b`) não acompanham os passos de reranking/CRAG.

## Testes

```bash
# Testes unitários (sem serviços externos)
python -m pytest tests/ -v

# Testes de integração (requer Qdrant + chaves de API)
python -m pytest tests/ -v -m integration

# Um ficheiro específico
python -m pytest tests/test_retriever.py -v
```

## Autora

Liane Duarte — al79012 — UTAD 2025/2026

**Orientadores:** Ricardo Costa (Teclab) · Paulo Oliveira · Eduardo Pires (UTAD)
