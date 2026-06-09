"""
Configuração central do sistema RAG farmacêutico.
Lê variáveis de ambiente do ficheiro .env.
"""

import os
from dotenv import load_dotenv

# override=False (default): as variaveis reais do ambiente (ex.: QDRANT_HOST=qdrant
# definido pelo docker-compose) tem precedencia sobre o .env. Com override=True, o
# .env montado no container (QDRANT_HOST=localhost) sobrepunha-se e a API procurava
# o Qdrant em localhost dentro do proprio container em vez do servico "qdrant".
load_dotenv()

# --- APIs ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- Qdrant ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "farmacos")

# --- Modelos ---
EMBEDDING_MODEL = "gemini-embedding-2-preview"
GENERATIVE_MODEL = "claude-sonnet-4-6"
EMBEDDING_DIMENSION = 3072

# --- LLM local (Ollama) ---
# Endereco do servidor Ollama e modelo a usar quando o modo "local" esta ativo.
# Em producao podem apontar para um Ollama noutro host ou usar modelo maior.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

# Modo LLM por defeito quando a BD ainda nao tem definicao guardada.
# "online" usa Claude (qualidade maxima); "local" usa Ollama (privacidade).
LLM_MODE_DEFAULT = os.getenv("LLM_MODE_DEFAULT", "online")

# --- Chunking ---
# RecursiveCharacterTextSplitter conta caracteres.
# ~4 chars/token em português → 4000 chars ≈ 1000 tokens.
CHUNK_SIZE = 4000       # caracteres (~1000 tokens)
CHUNK_OVERLAP = 800     # caracteres (~200 tokens)

# --- Recuperação ---
RETRIEVAL_TOP_K = 7     # chunks recuperados antes do reranking
RERANK_TOP_N = 3        # chunks após reranking (LLM-as-Judge)

# --- Guardrails ---
FAITHFULNESS_THRESHOLD = 0.85   # abaixo disto → flag na resposta
RELEVANCE_THRESHOLD = 0.80      # abaixo disto → CRAG reformula query

# --- Optimização CRAG ---
# Se o score do top chunk após reranking for >= a este valor, salta a
# avaliação CRAG (poupa 1 chamada LLM). O reranker é ele próprio um juiz LLM,
# pelo que scores altos já indicam contexto suficiente.
SKIP_CRAG_THRESHOLD = 0.85

# --- Diretórios ---
DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "documents")

# --- Autenticação ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRA_MINUTOS = int(os.getenv("JWT_EXPIRA_MINUTOS", "480"))  # 8h (um turno de trabalho)

# Base de dados SQLite dos utilizadores
AUTH_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "auth.db")

# Passwords das contas iniciais (seed) — lidas do .env, nunca versionadas
SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD")
SEED_FARMACEUTICO_PASSWORD = os.getenv("SEED_FARMACEUTICO_PASSWORD")
