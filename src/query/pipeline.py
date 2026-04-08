"""
Pipeline de consulta completo.

Orquestra todas as etapas do pipeline RAG:
  1. Validacao de input (guardrail)
  2. Recuperacao hibrida (Qdrant)
  3. Reranking (LLM-as-Judge)
  4. Avaliacao CRAG (relevancia + reformulacao)
  5. Geracao de resposta (Claude)
  6. Validacao de output (guardrail)

Uso:
    python -m src.query.pipeline "Quais sao os efeitos secundarios do ibuprofeno?"
"""

import argparse
import time
from functools import partial

from src.guardrails.input_guard import validar_input
from src.guardrails.output_guard import validar_output
from src.query.retriever import recuperar
from src.query.reranker import rerankar
from src.query.crag import crag_pipeline
from src.query.generator import gerar_resposta, RespostaRAG


def consultar(
    query: str,
    tipo_documento: str | None = None,
    verbose: bool = True,
) -> RespostaRAG:
    """
    Executa o pipeline de consulta completo.

    Args:
        query: Pergunta do utilizador em linguagem natural.
        tipo_documento: Filtro opcional por tipo de documento.
        verbose: Se True, imprime progresso no terminal.

    Returns:
        RespostaRAG com a resposta, fontes e metadados.
    """
    inicio = time.time()

    if verbose:
        print(f"\n=== PIPELINE DE CONSULTA ===")
        print(f"Query: {query}\n")

    # 1. Validacao de input
    if verbose:
        print("-- Etapa 1: Validacao de input --")
    valido, msg_erro = validar_input(query)
    if not valido:
        if verbose:
            print(f"   REJEITADO: {msg_erro}\n")
        return RespostaRAG(
            resposta=msg_erro,
            query_usada=query,
            contexto_suficiente=False,
            chunks_usados=[],
            fontes=[],
        )
    if verbose:
        print("   Input valido.\n")

    # 2. Recuperacao hibrida
    if verbose:
        print("-- Etapa 2: Recuperacao hibrida --")
    chunks = recuperar(query, tipo_documento=tipo_documento)
    if verbose:
        print(f"   {len(chunks)} chunk(s) recuperado(s)\n")

    # 3. Reranking
    if verbose:
        print("-- Etapa 3: Reranking (LLM-as-Judge) --")
    chunks_rerankados = rerankar(query, chunks)
    if verbose:
        print(f"   {len(chunks_rerankados)} chunk(s) apos reranking\n")

    # 4. CRAG — avaliacao de relevancia
    if verbose:
        print("-- Etapa 4: Avaliacao CRAG --")

    # Funcao parcial para re-recuperacao (usada pelo CRAG se reformular)
    def _recuperar_e_rerankar(nova_query: str) -> list:
        novos_chunks = recuperar(nova_query, tipo_documento=tipo_documento)
        return rerankar(nova_query, novos_chunks)

    chunks_finais, contexto_suficiente, query_usada = crag_pipeline(
        query, chunks_rerankados, recuperar_fn=_recuperar_e_rerankar,
    )
    if verbose:
        print(f"   Contexto suficiente: {contexto_suficiente}")
        if query_usada != query:
            print(f"   Query reformulada: {query_usada}")
        print()

    # 5. Geracao de resposta
    if verbose:
        print("-- Etapa 5: Geracao de resposta --")
    resultado = gerar_resposta(
        query=query,
        chunks=chunks_finais,
        contexto_suficiente=contexto_suficiente,
        query_usada=query_usada,
    )
    if verbose:
        print("   Resposta gerada.\n")

    # 6. Validacao de output
    if verbose:
        print("-- Etapa 6: Validacao de output --")
    valido, resposta_final, detalhes = validar_output(resultado.resposta, chunks_finais)
    resultado.resposta = resposta_final
    if verbose:
        print(f"   Fidelidade: {detalhes.get('fidelidade', '?')}")
        print(f"   Output valido: {valido}\n")

    duracao = time.time() - inicio
    if verbose:
        print(f"=== Pipeline concluido em {duracao:.1f}s ===\n")
        print("RESPOSTA:")
        print("-" * 60)
        print(resultado.resposta)
        print("-" * 60)
        print(f"\nFontes: {resultado.fontes}")

    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de consulta RAG farmaceutico")
    parser.add_argument("query", type=str, help="Pergunta em linguagem natural")
    parser.add_argument("--tipo", type=str, default=None,
                        help="Filtro por tipo de documento (bula, monografia, guideline, norma)")
    args = parser.parse_args()

    consultar(args.query, tipo_documento=args.tipo)
