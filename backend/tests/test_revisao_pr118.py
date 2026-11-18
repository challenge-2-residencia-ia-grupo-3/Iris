"""Teste de regressão do ponto levantado na revisão do PR #118 (histórico de eficácia das intervenções)."""
from __future__ import annotations

import unittest

from iris.schemas.portable_profile import PerfilInvalidoError, criar_perfil, registrar_intervencao

ID = "atencao_sustentada_textos_longos"
CPF, TELEFONE, EMAIL = "123.456.789-09", "99999-1234", "responsavel@escola.example"


class TestHistoricoSemDadoPessoal(unittest.TestCase):
    """O perfil devolvido vai para o localStorage do navegador: documento e contato não podem ir junto."""

    def test_observacao_e_estrategia_saem_com_marcador(self):
        p = registrar_intervencao(criar_perfil([ID]), f"Checklist; contato {EMAIL}", ID, "alta",
                                  f"CPF {CPF}, tel (61) {TELEFONE}, rendeu bem.")
        r = p.historico_intervencoes[-1]
        texto = f"{r.estrategia} {r.observacao}"
        for dado in (CPF, TELEFONE, EMAIL):
            self.assertNotIn(dado, texto)
        for marcador in ("[CPF]", "[TELEFONE]", "[EMAIL]"):
            self.assertIn(marcador, texto)
        self.assertIn("rendeu bem.", r.observacao)

    def test_texto_sem_dado_pessoal_nao_muda(self):
        p = registrar_intervencao(criar_perfil([ID]), "Fragmentação em checklist", ID, "media",
                                  "Terminou as 4 questões em 2026 sem pular etapas.")
        r = p.historico_intervencoes[-1]
        self.assertEqual(r.estrategia, "Fragmentação em checklist")
        self.assertEqual(r.observacao, "Terminou as 4 questões em 2026 sem pular etapas.")

    def test_bloqueio_clinico_continua(self):
        with self.assertRaises(PerfilInvalidoError):
            registrar_intervencao(criar_perfil([ID]), "Checklist", ID, "alta", f"CPF {CPF}; depois do laudo de TDAH melhorou")


if __name__ == "__main__":
    unittest.main()
