"""Testes do removedor de dado pessoal (`iris.security.pii_scrubber`) nos casos de número: CPF sem pontuação,
número longo do enunciado (ISBN, código de barras, valor decimal), intervalo de anos e telefone colado depois de
abreviação com ponto. Todos os valores são fictícios (CPF começado em 000, DDD 00)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
for p in (str(SRC_DIR), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris.security.pii_scrubber import sanitize_pii


def _cpf_com_verificadores(base9: str) -> str:
    """Monta um CPF fictício (começa em 000) com dígitos verificadores válidos, só para o teste."""
    d = [int(c) for c in base9]
    for tamanho in (9, 10):
        d.append(sum(d[i] * (tamanho + 1 - i) for i in range(tamanho)) * 10 % 11 % 10)
    return "".join(map(str, d))


class TestRemovedorDeDadoPessoal(unittest.TestCase):
    def test_cpf_sem_pontuacao_sai_inteiro_e_com_o_marcador_certo(self) -> None:
        cpf = _cpf_com_verificadores("000123456")
        self.assertEqual(sanitize_pii(f"CPF: {cpf}"), ("CPF: [CPF]", 1))
        self.assertEqual(sanitize_pii("CPF: 00012345678"), ("CPF: [TELEFONE]", 1))  # verificadores inválidos
        self.assertEqual(sanitize_pii("Celular: 00991234567"), ("Celular: [TELEFONE]", 1))

    def test_numero_longo_do_enunciado_nao_perde_pedaco(self) -> None:
        for texto in ("O ISBN 9788535902778 do livro", "Código de barras 7891234567895", "Valor 123.45678901"):
            self.assertEqual(sanitize_pii(texto), (texto, 0), texto)

    def test_intervalo_de_anos_e_conteudo_e_telefone_continua_saindo(self) -> None:
        for texto in ("Frei Vicente de Salvador (1564-1633)", "Segunda Guerra Mundial (1939-1945)", "No ano de 2020"):
            self.assertEqual(sanitize_pii(texto), (texto, 0), texto)
        self.assertEqual(sanitize_pii("Telefone da escola 3333-4444"), ("Telefone da escola [TELEFONE]", 1))
        self.assertEqual(sanitize_pii("Tel.: (00) 91234-5678"), ("Tel.: [TELEFONE]", 1))

    def test_telefone_colado_depois_de_abreviacao_com_ponto_sai(self) -> None:
        # a borda contra casas decimais não pode recusar todo número depois de ponto
        self.assertEqual(sanitize_pii("Tel.00912345678 recado"), ("Tel.[TELEFONE] recado", 1))
        self.assertEqual(sanitize_pii("Cel.3333-4444"), ("Cel.[TELEFONE]", 1))
        # e continua valendo quando antes do ponto há dígito
        for texto in ("ISBN 9788535902778 do livro", "O código 12.3333-4444 identifica o lote"):
            self.assertEqual(sanitize_pii(texto), (texto, 0), texto)

    def test_nenhuma_das_questoes_reais_do_benchmark_perde_texto(self) -> None:
        from iris.eval.rag_escolar_benchmark import carregar_questoes_curadas

        alteradas = [q.id for q in carregar_questoes_curadas() if sanitize_pii(q.texto_completo)[0] != q.texto_completo]
        self.assertEqual(alteradas, [])


if __name__ == "__main__":
    unittest.main()
