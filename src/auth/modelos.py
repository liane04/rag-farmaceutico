"""
Schemas Pydantic para autenticacao e gestao de utilizadores.

Define o utilizador (representacao publica e representacao em base de
dados) e os modelos associados ao token JWT.
"""

from typing import Literal

from pydantic import BaseModel, Field


# Papeis de utilizador suportados pelo sistema.
Papel = Literal["farmaceutico", "admin"]


class Utilizador(BaseModel):
    """Representacao publica de um utilizador (sem dados sensiveis)."""
    username: str = Field(description="Nome de utilizador unico.")
    papel: Papel = Field(description="Papel do utilizador: 'farmaceutico' ou 'admin'.")


class UtilizadorEmBD(Utilizador):
    """Utilizador tal como guardado na base de dados, com o hash da password."""
    id: int = Field(description="Identificador interno (chave primaria).")
    password_hash: str = Field(description="Hash bcrypt da password (nunca a password em claro).")
    criado_em: str = Field(description="Data/hora de criacao da conta (ISO 8601).")


class Token(BaseModel):
    """Token de acesso devolvido apos um login com sucesso."""
    access_token: str = Field(description="Token JWT assinado.")
    token_type: str = Field(default="bearer", description="Tipo de token (sempre 'bearer').")


class DadosToken(BaseModel):
    """Dados extraidos de um token JWT valido."""
    username: str = Field(description="Username do utilizador autenticado.")
    papel: Papel = Field(description="Papel do utilizador autenticado.")


class RegistoConsulta(BaseModel):
    """Registo de uma consulta ao sistema RAG (auditoria e historico)."""
    id: int = Field(description="Identificador do registo.")
    session_id: str | None = Field(default=None, description="Identificador da sessao de chat.")
    timestamp: str = Field(description="Data/hora da consulta (ISO 8601).")
    utilizador: str | None = Field(default=None, description="Username do utilizador (None se anonimo).")
    papel: str | None = Field(default=None, description="Papel do utilizador.")
    query_original: str = Field(description="Pergunta original do utilizador.")
    query_usada: str | None = Field(default=None, description="Query apos reformulacao.")
    contexto_suficiente: bool | None = Field(default=None, description="Flag do CRAG.")
    resposta: str | None = Field(default=None, description="Resposta gerada.")
    fontes: list[dict] = Field(default_factory=list, description="Fontes documentais citadas.")
    num_chunks: int | None = Field(default=None, description="Numero de chunks usados.")
    duracao_segundos: float | None = Field(default=None, description="Tempo total do pipeline.")
    fidelidade: float | None = Field(default=None, description="Score de fidelidade do output guard.")
    ip_cliente: str | None = Field(default=None, description="IP do cliente.")
