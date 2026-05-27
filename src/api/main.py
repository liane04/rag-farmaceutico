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

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, StreamingResponse
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
from src.auth.dependencias import requer_admin, utilizador_atual, utilizador_atual_query
from src.auth.modelos import DadosToken, Token, Utilizador


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa a base de dados e cria as contas iniciais no arranque da API."""
    from src.auth.db import inicializar_bd
    from src.auth.seed import correr_seed
    inicializar_bd()
    try:
        correr_seed()
    except RuntimeError as e:
        logger.critical("ERRO DE CONFIGURACAO: %s", e)
        raise
    yield


app = FastAPI(
    title="RAG Farmaceutico",
    description="Sistema de Retrieval-Augmented Generation para suporte a decisao farmaceutica.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — permitir acesso de qualquer origem (ajustar em producao)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Autenticação ---


@app.post(
    "/auth/login",
    response_model=Token,
    responses={401: {"model": ErroResponse}},
    summary="Autenticar e obter token de acesso",
    description="Recebe username e password (formulario) e devolve um token JWT de acesso.",
)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    from src.auth.db import obter_utilizador
    from src.auth.seguranca import criar_token, verificar_password

    utilizador = obter_utilizador(form.username)
    if utilizador is None or not verificar_password(form.password, utilizador.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username ou password incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = criar_token(utilizador.username, utilizador.papel)
    return Token(access_token=token)


@app.get(
    "/auth/me",
    response_model=Utilizador,
    summary="Dados do utilizador autenticado",
    description="Devolve o username e o papel do utilizador associado ao token.",
)
async def auth_me(utilizador: DadosToken = Depends(utilizador_atual)):
    return Utilizador(username=utilizador.username, papel=utilizador.papel)


@app.post(
    "/consulta",
    response_model=ConsultaResponse,
    responses={400: {"model": ErroResponse}, 422: {"model": ErroResponse}},
    summary="Consultar o sistema RAG",
    description="Envia uma pergunta em linguagem natural e recebe uma resposta fundamentada com citacoes.",
)
async def consulta(
    pedido: ConsultaRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    utilizador: DadosToken = Depends(utilizador_atual),
):
    from src.query.pipeline import consultar

    inicio = time.time()

    try:
        resultado = consultar(
            query=pedido.query,
            tipo_documento=pedido.tipo_documento,
            historia=pedido.historia,
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

    # Auditoria em background — nao bloqueia a resposta ao utilizador.
    background_tasks.add_task(
        registar_consulta,
        query_original=pedido.query,
        query_usada=resultado.query_usada,
        contexto_suficiente=resultado.contexto_suficiente,
        resposta=resultado.resposta,
        fontes=fontes_dict,
        num_chunks=len(resultado.chunks_usados),
        duracao_segundos=duracao,
        ip_cliente=request.client.host if request.client else None,
        session_id=pedido.session_id,
        utilizador=utilizador.username,
        papel=utilizador.papel,
    )

    return ConsultaResponse(
        resposta=resultado.resposta,
        query_usada=resultado.query_usada,
        contexto_suficiente=resultado.contexto_suficiente,
        fontes=[FonteResponse(**f) for f in fontes_dict],
        num_chunks_usados=len(resultado.chunks_usados),
    )


@app.post(
    "/consulta/stream",
    summary="Consulta com streaming (Server-Sent Events)",
    description="Versao streaming de /consulta. Devolve eventos SSE: meta (fontes + chunks), "
                "token (pedacos de texto da resposta), done (fidelidade + duracao), error. "
                "Mesma forma de pedido que /consulta.",
)
async def consulta_stream(
    pedido: ConsultaRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    utilizador: DadosToken = Depends(utilizador_atual),
):
    import json

    from src.query.pipeline import consultar_stream

    inicio = time.time()
    ip_cliente = request.client.host if request.client else None

    def gerar_eventos():
        # Estado capturado durante o stream para auditar no fim
        meta_recebida = {}
        resposta_final = ""
        duracao = 0.0
        fidelidade = None

        try:
            for evento in consultar_stream(
                query=pedido.query,
                tipo_documento=pedido.tipo_documento,
                historia=pedido.historia,
            ):
                # Capturar dados para a auditoria sem alterar o evento
                if evento["tipo"] == "meta":
                    meta_recebida = evento
                elif evento["tipo"] == "done":
                    resposta_final = evento.get("resposta_completa", "")
                    duracao = evento.get("duracao_segundos", 0.0)
                    fidelidade = evento.get("fidelidade")

                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        except Exception as e:
            erro = {"tipo": "error", "detalhe": str(e), "etapa": "pipeline"}
            yield f"data: {json.dumps(erro, ensure_ascii=False)}\n\n"
            return

        # Auditoria em background — mesma assinatura que /consulta usa
        if meta_recebida:
            fontes_dict = [
                {"ficheiro": f.get("ficheiro"), "pagina": f.get("pagina"), "tipo_documento": f.get("tipo_documento")}
                for f in meta_recebida.get("fontes", [])
            ]
            background_tasks.add_task(
                registar_consulta,
                query_original=pedido.query,
                query_usada=meta_recebida.get("query_usada", pedido.query),
                contexto_suficiente=meta_recebida.get("contexto_suficiente", False),
                resposta=resposta_final,
                fontes=fontes_dict,
                num_chunks=meta_recebida.get("num_chunks_usados", 0),
                duracao_segundos=duracao if duracao else (time.time() - inicio),
                fidelidade=fidelidade,
                ip_cliente=ip_cliente,
                session_id=pedido.session_id,
                utilizador=utilizador.username,
                papel=utilizador.papel,
            )

    return StreamingResponse(
        gerar_eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # desactiva buffering em proxies (nginx)
            "Connection": "keep-alive",
        },
    )


@app.post(
    "/ingestao",
    response_model=IngestaoResponse,
    summary="Ingerir documentos",
    description="Corre o pipeline de ingestao para todos os PDFs na pasta data/documents.",
)
async def ingestao(_: DadosToken = Depends(requer_admin)):
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
    except Exception as e:
        return HealthResponse(
            status="degradado",
            qdrant=f"erro: {str(e)}",
            collection=QDRANT_COLLECTION,
            total_pontos=0,
        )

    try:
        if not cliente.collection_exists(QDRANT_COLLECTION):
            return HealthResponse(
                status="vazio",
                qdrant="conectado",
                collection=QDRANT_COLLECTION,
                total_pontos=0,
            )
        info = cliente.get_collection(QDRANT_COLLECTION)
        total = info.points_count or 0
        return HealthResponse(
            status="ok" if total > 0 else "vazio",
            qdrant="conectado",
            collection=QDRANT_COLLECTION,
            total_pontos=total,
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
async def documentos(_: DadosToken = Depends(utilizador_atual)):
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
    summary="Consultar registos de auditoria",
    description="Devolve os registos de auditoria mais recentes (todas as consultas ao sistema).",
)
async def audit(limite: int = 200, _: DadosToken = Depends(requer_admin)):
    from src.auth.db import listar_consultas

    registos = listar_consultas(limite=limite)
    return {"registos": registos, "total": len(registos)}


@app.get(
    "/historico",
    summary="Histórico de consultas do utilizador",
    description="Devolve as consultas anteriores do utilizador autenticado.",
)
async def historico(utilizador: DadosToken = Depends(utilizador_atual), limite: int = 100):
    from src.auth.db import listar_consultas_por_utilizador

    registos = listar_consultas_por_utilizador(utilizador.username, limite=limite)
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
    _: DadosToken = Depends(requer_admin),
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


@app.get(
    "/ficheiros/{tipo}/{nome}",
    summary="Servir um PDF da pasta de documentos",
    description="Devolve o ficheiro PDF original (bula, monografia, etc.) para visualizacao no browser. "
                "Usar com sufixo #page=N para abrir directamente numa pagina especifica.",
)
async def ficheiro(
    tipo: str,
    nome: str,
    _: DadosToken = Depends(utilizador_atual_query),
):
    tipos_validos = {"bula": "bulas", "monografia": "monografias", "guideline": "guidelines", "norma": "normas"}
    if tipo not in tipos_validos:
        raise HTTPException(status_code=404, detail=f"Tipo invalido: {tipo}")

    # Defesa contra directory traversal: rejeita separadores, paths absolutos
    # e qualquer tentativa de subir niveis. O nome tem de ser um ficheiro simples.
    if "/" in nome or "\\" in nome or ".." in nome or Path(nome).name != nome:
        raise HTTPException(status_code=400, detail="Nome de ficheiro invalido.")
    if not nome.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas ficheiros PDF sao servidos.")

    pasta_base = Path(__file__).parent.parent.parent / "data" / "documents"
    caminho = pasta_base / tipos_validos[tipo] / nome

    # Resolve e verifica que o caminho final continua dentro da pasta esperada
    # (defesa em profundidade contra symlinks ou paths construidos manualmente).
    try:
        caminho_resolvido = caminho.resolve()
        pasta_resolvida = (pasta_base / tipos_validos[tipo]).resolve()
        caminho_resolvido.relative_to(pasta_resolvida)
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Caminho invalido.")

    if not caminho_resolvido.is_file():
        raise HTTPException(status_code=404, detail=f"Ficheiro nao encontrado: {nome}")

    return FileResponse(caminho_resolvido, media_type="application/pdf", filename=nome)


# --- Interface web ---

STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def interface():
    """Serve a interface web."""
    return FileResponse(STATIC_DIR / "index.html")
