FROM python:3.12-slim

WORKDIR /app

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar codigo fonte
COPY src/ ./src/

# Criar diretorios necessarios (serao sobrepostos pelo volume em compose)
RUN mkdir -p data/documents/bulas \
             data/documents/monografias \
             data/documents/guidelines \
             data/documents/normas \
             data/audit

# Variavel de ambiente para Python nao bufferizar output
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
