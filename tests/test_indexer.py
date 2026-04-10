"""
Testes para o indexer (src/ingestion/indexer.py).

Testes unitarios que nao precisam do Qdrant a correr.
"""

import uuid

from src.ingestion.indexer import _texto_para_sparse
from src.ingestion.chunker import Chunk


class TestTextoParaSparse:
    """Testes para a funcao _texto_para_sparse."""

    def test_retorna_sparse_vector(self):
        sparse = _texto_para_sparse("ibuprofeno comprimido oral")
        assert hasattr(sparse, "indices")
        assert hasattr(sparse, "values")
        assert len(sparse.indices) > 0
        assert len(sparse.values) > 0

    def test_indices_e_values_mesmo_tamanho(self):
        sparse = _texto_para_sparse("ibuprofeno 400mg comprimido revestido")
        assert len(sparse.indices) == len(sparse.values)

    def test_deterministico(self):
        texto = "efeitos secundarios do ibuprofeno"
        sparse1 = _texto_para_sparse(texto)
        sparse2 = _texto_para_sparse(texto)
        assert sparse1.indices == sparse2.indices
        assert sparse1.values == sparse2.values

    def test_frequencia_refletida(self):
        # "ibuprofeno" aparece 2x, deve ter peso maior
        sparse = _texto_para_sparse("ibuprofeno ibuprofeno comprimido")
        # O valor para o indice do "ibuprofeno" deve ser >= 2
        assert max(sparse.values) >= 2.0

    def test_texto_vazio(self):
        sparse = _texto_para_sparse("")
        assert len(sparse.indices) == 0
        assert len(sparse.values) == 0

    def test_indices_unicos(self):
        sparse = _texto_para_sparse("ibuprofeno comprimido oral febre dor")
        assert len(sparse.indices) == len(set(sparse.indices))


class TestIdsDeterministicos:
    """Testes para verificar que os IDs gerados sao deterministicos."""

    def test_mesmo_chunk_mesmo_id(self):
        chave1 = "brufen.pdf:1:0"
        chave2 = "brufen.pdf:1:0"
        id1 = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave1))
        id2 = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave2))
        assert id1 == id2

    def test_chunks_diferentes_ids_diferentes(self):
        chave1 = "brufen.pdf:1:0"
        chave2 = "brufen.pdf:1:1"
        id1 = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave1))
        id2 = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave2))
        assert id1 != id2

    def test_ficheiros_diferentes_ids_diferentes(self):
        chave1 = "brufen.pdf:1:0"
        chave2 = "brufen_folheto.pdf:1:0"
        id1 = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave1))
        id2 = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave2))
        assert id1 != id2
