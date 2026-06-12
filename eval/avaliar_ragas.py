"""
Avaliacao do pipeline RAG com metricas RAGAS (faithfulness, answer relevancy,
context precision, context recall).

O pipeline corre em modo ONLINE (Claude) sobre o dataset de avaliacao; o juiz
das metricas e tambem o Claude (via langchain-anthropic) e os embeddings sao
os do proprio sistema (Gemini). A pergunta de controlo (fora do corpus) e
avaliada mas excluida das medias.

Uso (a partir da raiz do repo, com Qdrant a correr e corpus indexado):
    python eval/avaliar_ragas.py                 # tudo: pipeline + metricas
    python eval/avaliar_ragas.py --limite 2      # smoke test com N perguntas
    python eval/avaliar_ragas.py --so-metricas   # reutiliza o cache de respostas

Outputs em eval/: cache_respostas.json, resultados_ragas.json, resultados_ragas.md
"""

# --- Shim: o ragas 0.4.3 importa modulos legacy removidos do
# langchain-community 0.4.x. Stubs satisfazem o import (usados so em
# isinstance() para modelos Vertex, que nao usamos). ---
import sys
import types


def _stub_module(nome: str, classes: list[str]) -> None:
    mod = types.ModuleType(nome)
    for c in classes:
        setattr(mod, c, type(c, (), {}))
    sys.modules[nome] = mod


try:
    from langchain_community.chat_models.vertexai import ChatVertexAI  # noqa: F401
except Exception:
    _stub_module("langchain_community.chat_models.vertexai", ["ChatVertexAI"])
try:
    from langchain_community.llms import VertexAI  # noqa: F401
except Exception:
    _stub_module("langchain_community.llms", ["VertexAI"])


import argparse
import json
import time
from datetime import datetime
from pathlib import Path

# Permite `python eval/avaliar_ragas.py` a partir da raiz do repo: o Python
# poe a pasta do script (eval/) no sys.path, nao o cwd — adicionamos a raiz
# para os imports `src.*` resolverem.
sys.path.insert(0, str(Path(__file__).parent.parent))

PASTA_EVAL = Path(__file__).parent
CAMINHO_DATASET = PASTA_EVAL / "dataset_avaliacao.json"


def _caminhos(modo: str) -> tuple[Path, Path, Path]:
    """Ficheiros de cache/resultados por modo — o online fica sem sufixo
    (canonico); o local escreve em *_local.* sem tocar nos resultados online."""
    sufixo = "" if modo == "online" else f"_{modo}"
    return (
        PASTA_EVAL / f"cache_respostas{sufixo}.json",
        PASTA_EVAL / f"resultados_ragas{sufixo}.json",
        PASTA_EVAL / f"resultados_ragas{sufixo}.md",
    )


def carregar_dataset() -> list[dict]:
    return json.loads(CAMINHO_DATASET.read_text(encoding="utf-8"))["perguntas"]


def correr_pipeline(perguntas: list[dict], modo: str = "online") -> list[dict]:
    """Corre consultar() no modo pedido para cada pergunta; devolve resultados."""
    from src.auth.db import inicializar_bd
    from src.llm_client import definir_modo_llm, obter_modo_llm
    from src.query.pipeline import consultar

    inicializar_bd()
    modo_original = obter_modo_llm()
    definir_modo_llm(modo)
    resultados = []
    try:
        for i, p in enumerate(perguntas, start=1):
            t0 = time.time()
            r = consultar(p["pergunta"], verbose=False)
            resultados.append({
                "id": p["id"],
                "pergunta": p["pergunta"],
                "referencia": p["referencia"],
                "controlo": p["controlo"],
                "resposta": r.resposta,
                "contextos": [c.texto for c in r.chunks_usados],
                "fontes": r.fontes,
                "contexto_suficiente": r.contexto_suficiente,
                "duracao_s": round(time.time() - t0, 1),
            })
            print(f"[pipeline {i}/{len(perguntas)}] {p['id']} "
                  f"({resultados[-1]['duracao_s']}s, "
                  f"suficiente={r.contexto_suficiente})", flush=True)
    finally:
        definir_modo_llm(modo_original)
    return resultados


JUIZ_MODELO = "claude-sonnet-4-6"

# Timeout por chamada de metrica — um juiz pendurado (retries de 429, rede)
# regista None e o run continua, em vez de bloquear em silencio.
TIMEOUT_METRICA_S = 240


def avaliar_com_ragas(resultados: list[dict]) -> tuple[list[str], list[dict]]:
    """
    Calcula as 4 metricas RAGAS sobre os resultados do pipeline.

    Juiz: Claude (o gerador partilha o modelo — limitacao de auto-avaliacao
    reconhecida na nota metodologica; o Gemini generativo da chave atual e
    free-tier com 20 pedidos/dia, insuficiente para ~50 julgamentos). As
    metricas sao chamadas diretamente (single_turn_ascore) em vez do
    evaluate(): a injecao de embeddings do evaluate() ignorava os nossos e
    usava um default com dimensionalidade diferente, rebentando a
    answer_relevancy.
    """
    import asyncio

    from langchain_anthropic import ChatAnthropic
    from ragas import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerRelevancy,
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )

    from src.config import ANTHROPIC_API_KEY
    from src.ingestion.embedder import criar_embedder

    juiz = LangchainLLMWrapper(ChatAnthropic(
        model=JUIZ_MODELO,
        api_key=ANTHROPIC_API_KEY,
        temperature=0,
        max_tokens=2000,
    ))

    from langchain_core.embeddings import Embeddings

    class _EmbeddingsPorTexto(Embeddings):
        """Bug do langchain-google-genai 4.2.2: embed_documents com varios
        textos devolve UM unico vetor (o reshape da answer_relevancy partia
        com (3,1024) vs 3072). Forcamos lotes de 1 texto — o mesmo contorno
        que o embedder do sistema ja faz via fallback individual."""

        def __init__(self, base):
            self._base = base

        def embed_documents(self, texts):
            return [self._base.embed_documents([t])[0] for t in texts]

        def embed_query(self, text):
            return self._base.embed_documents([text])[0]

    embeddings = LangchainEmbeddingsWrapper(_EmbeddingsPorTexto(criar_embedder()))

    metricas = [
        Faithfulness(llm=juiz),
        AnswerRelevancy(llm=juiz, embeddings=embeddings),
        LLMContextPrecisionWithReference(llm=juiz),
        LLMContextRecall(llm=juiz),
    ]
    cols = [m.name for m in metricas]

    amostras = [
        SingleTurnSample(
            user_input=r["pergunta"],
            response=r["resposta"],
            retrieved_contexts=r["contextos"] or [""],
            reference=r["referencia"],
        )
        for r in resultados
    ]

    async def _pontuar():
        linhas = []
        for i, amostra in enumerate(amostras, start=1):
            linha = {}
            for m in metricas:
                try:
                    score = await asyncio.wait_for(
                        m.single_turn_ascore(amostra), timeout=TIMEOUT_METRICA_S)
                    linha[m.name] = round(float(score), 3)
                except Exception as e:  # timeout/falha individual — segue
                    print(f"  [aviso] {m.name} falhou em {resultados[i-1]['id']}: {str(e)[:90]}")
                    linha[m.name] = None
            linhas.append(linha)
            print(f"[metricas {i}/{len(amostras)}] {resultados[i-1]['id']}: {linha}", flush=True)
        return linhas

    return cols, asyncio.run(_pontuar())


def gerar_relatorio(resultados: list[dict], cols: list[str], scores: list[dict],
                    modo: str, caminho_json: Path, caminho_md: Path) -> None:
    linhas = []
    for r, s in zip(resultados, scores):
        linhas.append({
            "id": r["id"], "controlo": r["controlo"],
            "contexto_suficiente": r["contexto_suficiente"],
            "duracao_s": r["duracao_s"], **s,
        })

    nucleo = [l for l in linhas if not l["controlo"]]
    medias = {c: round(sum(l[c] for l in nucleo if l[c] is not None)
                       / max(1, len([l for l in nucleo if l[c] is not None])), 3)
              for c in cols}

    if modo == "online":
        nota_juiz = (f"{JUIZ_MODELO} (partilha o modelo do gerador — auto-avaliacao parcial, "
                     "limitacao reconhecida; as metricas sao ancoradas nos contextos/referencias)")
    else:
        nota_juiz = (f"{JUIZ_MODELO} (independente do gerador local — juiz constante "
                     "entre os modos para comparabilidade)")

    payload = {
        "data": datetime.now().isoformat(timespec="seconds"),
        "modo_pipeline": modo,
        "juiz": nota_juiz,
        "n_perguntas": len(linhas),
        "n_nucleo": len(nucleo),
        "medias_nucleo": medias,
        "por_pergunta": linhas,
    }
    caminho_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Resultados da avaliacao RAGAS", ""]
    md.append(f"- Data: {payload['data']}")
    md.append(f"- Pipeline em modo **{modo}**; juiz: **{JUIZ_MODELO}** (constante entre modos); "
              "embeddings: Gemini (os do sistema)")
    md.append(f"- {len(nucleo)} perguntas do corpus + {len(linhas) - len(nucleo)} de controlo (fora do corpus, excluida das medias)")
    md.append("")
    md.append("## Medias (nucleo)")
    md.append("")
    md.append("| Metrica | Media |")
    md.append("|---|---|")
    for c in cols:
        md.append(f"| {c} | **{medias[c]}** |")
    md.append("")
    md.append("## Por pergunta")
    md.append("")
    md.append("| id | " + " | ".join(cols) + " | suficiente | duracao (s) |")
    md.append("|---|" + "---|" * (len(cols) + 2))
    for l in linhas:
        marca = " (controlo)" if l["controlo"] else ""
        valores = " | ".join("-" if l[c] is None else f"{l[c]}" for c in cols)
        md.append(f"| {l['id']}{marca} | {valores} | {l['contexto_suficiente']} | {l['duracao_s']} |")
    md.append("")
    md.append("> Nota metodologica: faithfulness e context precision/recall sao calculadas por LLM-juiz "
              f"({JUIZ_MODELO}). O juiz partilha o modelo do gerador (auto-avaliacao parcial — limitacao "
              "reconhecida; as metricas sao ancoradas nos contextos recuperados e nas referencias, nao em "
              "opiniao livre do juiz). Answer relevancy usa os embeddings do sistema. As referencias foram "
              "redigidas a partir do texto dos documentos oficiais do corpus.")
    caminho_md.write_text("\n".join(md), encoding="utf-8")
    print(f"\nResultados escritos em:\n  {caminho_json}\n  {caminho_md}")
    print(f"\nMedias (nucleo, modo {modo}):", json.dumps(medias, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliacao RAGAS do pipeline RAG")
    parser.add_argument("--modo", choices=["online", "local"], default="online",
                        help="Modo do pipeline a avaliar (default: online). O modo local "
                             "exige Ollama a correr; em CPU conta ~6 min por pergunta.")
    parser.add_argument("--limite", type=int, default=None,
                        help="Avaliar apenas as primeiras N perguntas (smoke test)")
    parser.add_argument("--so-metricas", action="store_true",
                        help="Saltar o pipeline e reutilizar o cache de respostas do modo")
    args = parser.parse_args()

    caminho_cache, caminho_json, caminho_md = _caminhos(args.modo)
    perguntas = carregar_dataset()
    if args.limite:
        perguntas = perguntas[: args.limite]

    if args.so_metricas and caminho_cache.exists():
        resultados = json.loads(caminho_cache.read_text(encoding="utf-8"))
        if args.limite:
            resultados = resultados[: args.limite]
        print(f"A reutilizar {len(resultados)} respostas do cache ({caminho_cache.name}).")
    else:
        resultados = correr_pipeline(perguntas, modo=args.modo)
        caminho_cache.write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Cache de respostas escrito em {caminho_cache}")

    print("\nA calcular metricas RAGAS (LLM-juiz)...", flush=True)
    cols, scores = avaliar_com_ragas(resultados)
    gerar_relatorio(resultados, cols, scores, args.modo, caminho_json, caminho_md)


if __name__ == "__main__":
    main()
