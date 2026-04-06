python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
