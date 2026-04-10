"""
Testes para o guardrail de output (src/guardrails/output_guard.py).

Testes de detecao de disclaimer (sem chamadas ao Claude).
"""

from src.guardrails.output_guard import verificar_disclaimer


class TestVerificarDisclaimer:
    """Testes para detecao do disclaimer obrigatorio."""

    def test_disclaimer_completo_com_acentos(self):
        resposta = """Aqui esta a resposta.

        AVISO: Esta informacao destina-se apenas a apoio a decisao.
        Nao substitui o julgamento clinico do profissional de saude
        nem a consulta da documentacao original. Verifique sempre as fontes citadas."""
        tem, _ = verificar_disclaimer(resposta)
        assert tem is True

    def test_disclaimer_completo_sem_acentos(self):
        resposta = """Aqui esta a resposta.

        AVISO: Nao substitui o julgamento do profissional de saude.
        Consulte a documentacao original."""
        tem, _ = verificar_disclaimer(resposta)
        assert tem is True

    def test_disclaimer_com_acentos_unicode(self):
        resposta = """Resposta sobre ibuprofeno.

        AVISO: Esta informação é gerada automaticamente. Não substitui
        o julgamento clínico do profissional de saúde nem a consulta
        da documentação original. Verifique sempre as fontes citadas."""
        tem, _ = verificar_disclaimer(resposta)
        assert tem is True

    def test_sem_disclaimer(self):
        resposta = "O ibuprofeno e um anti-inflamatorio."
        tem, _ = verificar_disclaimer(resposta)
        assert tem is False

    def test_disclaimer_parcial_insuficiente(self):
        # Apenas 1 keyword - precisa de pelo menos 2
        resposta = "Resposta. AVISO: consulte um profissional."
        tem, _ = verificar_disclaimer(resposta)
        assert tem is False

    def test_resposta_vazia(self):
        tem, _ = verificar_disclaimer("")
        assert tem is False
