"""
API REST do sistema RAG farmaceutico (FastAPI).

Endpoints:
  POST /consulta         — consulta ao sistema RAG
  POST /ingestao         — ingerir documentos de uma pasta
  GET  /health           — estado do sistema
  GET  /audit            — consultar logs de auditoria

Uso:
    uvicorn src.api.main:app --reload --port 8000
"""

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.models import (
    ConsultaRequest,
    ConsultaResponse,
    DocumentoResponse,
    DocumentosListResponse,
    ErroResponse,
    FonteResponse,
    HealthResponse,
    IngestaoResponse,
)
from src.api.audit import registar_consulta
from src.config import QDRANT_COLLECTION


app = FastAPI(
    title="RAG Farmaceutico",
    description="Sistema de Retrieval-Augmented Generation para suporte a decisao farmaceutica.",
    version="1.0.0",
)

# CORS — permitir acesso de qualquer origem (ajustar em producao)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post(
    "/consulta",
    response_model=ConsultaResponse,
    responses={400: {"model": ErroResponse}, 422: {"model": ErroResponse}},
    summary="Consultar o sistema RAG",
    description="Envia uma pergunta em linguagem natural e recebe uma resposta fundamentada com citacoes.",
)
async def consulta(pedido: ConsultaRequest, request: Request):
    from src.query.pipeline import consultar

    inicio = time.time()

    try:
        resultado = consultar(
            query=pedido.query,
            tipo_documento=pedido.tipo_documento,
            verbose=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    duracao = time.time() - inicio

    # Registar auditoria
    fontes_dict = [
        {"ficheiro": f.get("ficheiro"), "pagina": f.get("pagina"), "tipo_documento": f.get("tipo_documento")}
        for f in resultado.fontes
    ]

    registar_consulta(
        query_original=pedido.query,
        query_usada=resultado.query_usada,
        contexto_suficiente=resultado.contexto_suficiente,
        resposta=resultado.resposta,
        fontes=fontes_dict,
        num_chunks=len(resultado.chunks_usados),
        duracao_segundos=duracao,
        ip_cliente=request.client.host if request.client else None,
    )

    return ConsultaResponse(
        resposta=resultado.resposta,
        query_usada=resultado.query_usada,
        contexto_suficiente=resultado.contexto_suficiente,
        fontes=[FonteResponse(**f) for f in fontes_dict],
        num_chunks_usados=len(resultado.chunks_usados),
    )


@app.post(
    "/ingestao",
    response_model=IngestaoResponse,
    summary="Ingerir documentos",
    description="Corre o pipeline de ingestao para todos os PDFs na pasta data/documents.",
)
async def ingestao():
    from src.ingestion.pipeline import correr_pipeline_pasta
    from src.ingestion.indexer import criar_cliente, contar_pontos

    pasta = Path(__file__).parent.parent.parent / "data" / "documents"
    if not pasta.is_dir():
        raise HTTPException(status_code=404, detail="Pasta data/documents nao encontrada.")

    inicio = time.time()

    # Capturar metricas do pipeline
    from src.ingestion.loader import carregar_pasta
    from src.ingestion.chunker import chunkar_documentos
    from src.ingestion.embedder import criar_embedder, gerar_embeddings
    from src.ingestion.indexer import indexar_chunks

    documentos = carregar_pasta(pasta)
    chunks = chunkar_documentos(documentos)
    embedder = criar_embedder()
    pares = gerar_embeddings(chunks, embedder)
    cliente = criar_cliente()
    total_indexado = indexar_chunks(pares, cliente)
    total_collection = contar_pontos(cliente)

    duracao = time.time() - inicio

    return IngestaoResponse(
        documentos_carregados=len(documentos),
        chunks_gerados=len(chunks),
        pontos_indexados=total_indexado,
        total_na_collection=total_collection,
        duracao_segundos=round(duracao, 1),
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado do sistema",
    description="Verifica se o Qdrant esta acessivel e quantos pontos existem na collection.",
)
async def health():
    from src.ingestion.indexer import criar_cliente

    try:
        cliente = criar_cliente()
        info = cliente.get_collection(QDRANT_COLLECTION)
        return HealthResponse(
            status="ok",
            qdrant="conectado",
            collection=QDRANT_COLLECTION,
            total_pontos=info.points_count,
        )
    except Exception as e:
        return HealthResponse(
            status="degradado",
            qdrant=f"erro: {str(e)}",
            collection=QDRANT_COLLECTION,
            total_pontos=0,
        )


@app.get(
    "/documentos",
    response_model=DocumentosListResponse,
    summary="Listar documentos indexados",
    description="Devolve a lista de documentos indexados no Qdrant com numero de chunks e paginas.",
)
async def documentos():
    from collections import defaultdict
    from src.ingestion.indexer import criar_cliente
    from qdrant_client.models import ScrollRequest

    try:
        cliente = criar_cliente()

        # Buscar todos os pontos (so metadados, sem vetores)
        registos = defaultdict(lambda: {"tipo": "desconhecido", "paginas": set(), "chunks": 0})
        offset = None
        while True:
            resultado = cliente.scroll(
                collection_name=QDRANT_COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            pontos, offset = resultado
            if not pontos:
                break
            for ponto in pontos:
                ficheiro = ponto.payload.get("ficheiro", "desconhecido")
                registos[ficheiro]["tipo"] = ponto.payload.get("tipo_documento", "desconhecido")
                registos[ficheiro]["paginas"].add(ponto.payload.get("pagina", 0))
                registos[ficheiro]["chunks"] += 1
            if offset is None:
                break

        docs = []
        for ficheiro, info in sorted(registos.items()):
            docs.append(DocumentoResponse(
                ficheiro=ficheiro,
                tipo_documento=info["tipo"],
                total_chunks=info["chunks"],
                paginas=sorted(info["paginas"]),
            ))

        return DocumentosListResponse(
            documentos=docs,
            total_documentos=len(docs),
            total_chunks=sum(d.total_chunks for d in docs),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/audit",
    summary="Consultar logs de auditoria",
    description="Devolve os registos de auditoria do dia atual.",
)
async def audit():
    import json
    from datetime import datetime, timezone
    from src.api.audit import AUDIT_DIR

    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ficheiro = AUDIT_DIR / f"audit_{hoje}.jsonl"

    if not ficheiro.exists():
        return {"registos": [], "total": 0}

    registos = []
    with open(ficheiro, "r", encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                registos.append(json.loads(linha))

    return {"registos": registos, "total": len(registos)}


@app.post(
    "/upload",
    response_model=IngestaoResponse,
    summary="Upload e ingestao de um PDF",
    description="Faz upload de um ficheiro PDF, coloca-o na subpasta correta e indexa-o no Qdrant.",
)
async def upload(
    ficheiro: UploadFile = File(..., description="Ficheiro PDF a ingerir"),
    tipo_documento: str = Form(..., description="Tipo: bula, monografia, guideline, norma"),
):
    import shutil

    # Validar tipo
    tipos_validos = {"bula": "bulas", "monografia": "monografias", "guideline": "guidelines", "norma": "normas"}
    if tipo_documento not in tipos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo invalido. Valores aceites: {', '.join(tipos_validos.keys())}",
        )

    # Validar extensao
    if not ficheiro.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas ficheiros PDF sao aceites.")

    # Guardar na subpasta correta
    pasta_base = Path(__file__).parent.parent.parent / "data" / "documents"
    pasta_destino = pasta_base / tipos_validos[tipo_documento]
    pasta_destino.mkdir(parents=True, exist_ok=True)

    caminho_ficheiro = pasta_destino / ficheiro.filename

    with open(caminho_ficheiro, "wb") as f:
        shutil.copyfileobj(ficheiro.file, f)

    # Ingerir o ficheiro
    inicio = time.time()

    from src.ingestion.loader import carregar_pdf
    from src.ingestion.chunker import chunkar_documento
    from src.ingestion.embedder import criar_embedder, gerar_embeddings
    from src.ingestion.indexer import criar_cliente, indexar_chunks, contar_pontos

    try:
        doc = carregar_pdf(caminho_ficheiro, tipo_documento=tipo_documento)
        chunks = chunkar_documento(doc)
        embedder = criar_embedder()
        pares = gerar_embeddings(chunks, embedder)
        cliente = criar_cliente()
        total_indexado = indexar_chunks(pares, cliente)
        total_collection = contar_pontos(cliente)
    except Exception as e:
        # Se falhar a ingestao, apagar o ficheiro
        caminho_ficheiro.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Erro na ingestao: {str(e)}")

    duracao = time.time() - inicio

    return IngestaoResponse(
        documentos_carregados=1,
        chunks_gerados=len(chunks),
        pontos_indexados=total_indexado,
        total_na_collection=total_collection,
        duracao_segundos=round(duracao, 1),
    )


# --- Interface web ---

STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def interface():
    """Serve a interface web."""
    return FileResponse(STATIC_DIR / "index.html")
