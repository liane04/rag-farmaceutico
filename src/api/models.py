"""
Schemas Pydantic para a API REST.

Define os modelos de request e response para validacao automatica
e documentacao no Swagger UI.
"""

from pydantic import BaseModel, Field


# --- Request ---

class ConsultaRequest(BaseModel):
    """Pedido de consulta ao sistema RAG."""
    query: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Pergunta em linguagem natural sobre farmacia/medicamentos.",
        examples=["Quais sao os efeitos secundarios do ibuprofeno?"],
    )
    tipo_documento: str | None = Field(
        default=None,
        description="Filtro opcional por tipo de documento: bula, monografia, guideline, norma.",
        examples=["bula"],
    )


# --- Response ---

class FonteResponse(BaseModel):
    """Fonte documental citada na resposta."""
    ficheiro: str
    pagina: int | None = None
    tipo_documento: str | None = None


class ConsultaResponse(BaseModel):
    """Resposta do sistema RAG a uma consulta."""
    resposta: str = Field(description="Resposta gerada com citacoes de fontes.")
    query_usada: str = Field(description="Query efetivamente usada (pode ter sido reformulada pelo CRAG).")
    contexto_suficiente: bool = Field(description="True se o CRAG considerou o contexto adequado.")
    fontes: list[FonteResponse] = Field(description="Lista de fontes documentais citadas.")
    num_chunks_usados: int = Field(description="Numero de chunks usados na geracao.")


class ErroResponse(BaseModel):
    """Resposta de erro."""
    erro: str
    detalhe: str | None = None


# --- Ingestao ---

class IngestaoResponse(BaseModel):
    """Resposta do pipeline de ingestao."""
    documentos_carregados: int
    chunks_gerados: int
    pontos_indexados: int
    total_na_collection: int
    duracao_segundos: float


# --- Documentos ---

class DocumentoResponse(BaseModel):
    """Informacao sobre um documento indexado."""
    ficheiro: str
    tipo_documento: str
    total_chunks: int
    paginas: list[int]


class DocumentosListResponse(BaseModel):
    """Lista de documentos indexados no sistema."""
    documentos: list[DocumentoResponse]
    total_documentos: int
    total_chunks: int


# --- Health ---

class HealthResponse(BaseModel):
    """Estado do sistema."""
    status: str
    qdrant: str
    collection: str
    total_pontos: int
