"""
Configuração central do sistema RAG farmacêutico.
Lê variáveis de ambiente do ficheiro .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- APIs ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- Qdrant ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "farmacos")

# --- Modelos ---
EMBEDDING_MODEL = "models/gemini-embedding-2-preview"
GENERATIVE_MODEL = "claude-3-5-sonnet-20241022"     # Claude 3.5 Sonnet
EMBEDDING_DIMENSION = 3072

# --- Chunking ---
# RecursiveCharacterTextSplitter conta caracteres.
# ~4 chars/token em português → 4000 chars ≈ 1000 tokens.
CHUNK_SIZE = 4000       # caracteres (~1000 tokens)
CHUNK_OVERLAP = 800     # caracteres (~200 tokens)

# --- Recuperação ---
RETRIEVAL_TOP_K = 10    # chunks recuperados antes do reranking
RERANK_TOP_N = 3        # chunks após reranking (LLM-as-Judge)

# --- Guardrails ---
FAITHFULNESS_THRESHOLD = 0.85   # abaixo disto → flag na resposta
RELEVANCE_THRESHOLD = 0.80      # abaixo disto → CRAG reformula query

# --- Diretórios ---
DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "documents")
