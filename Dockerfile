FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias do sistema necessarias para pymupdf e pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar codigo fonte
COPY src/ ./src/
COPY data/ ./data/

# Criar diretorios necessarios
RUN mkdir -p data/documents/bulas \
             data/documents/monografias \
             data/documents/guidelines \
             data/documents/normas \
             data/audit

# Variavel de ambiente para Python nao bufferizar output
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
