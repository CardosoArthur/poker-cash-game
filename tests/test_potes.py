"""Divisão do pote, side pots e fichas ímpares."""
import unittest

from poker.avaliador import avaliar
from poker.cartas import cartas
from poker.potes import calcular_potes, distribuir_potes


class TestCalcularPotes(unittest.TestCase):
    def test_pote_unico(self):
        potes = calcular_potes({"A": 100, "B": 100, "C": 100})
        self.assertEqual(len(potes), 1)
        self.assertEqual(potes[0].valor, 300)
        self.assertEqual(potes[0].elegiveis, ["A", "B", "C"])

    def test_tres_all_ins_diferentes(self):
        potes = calcular_potes({"A": 50, "B": 150, "C": 300, "D": 300})
        self.assertEqual([p.valor for p in potes], [200, 300, 300])
        self.assertEqual([p.elegiveis for p in potes],
                         [["A", "B", "C", "D"], ["B", "C", "D"], ["C", "D"]])

    def test_desistente_paga_mas_nao_concorre(self):
        potes = calcular_potes({"A": 100, "B": 40, "C": 100}, desistiram=["B"])
        self.assertEqual(sum(p.valor for p in potes), 240)
        self.assertEqual(len(potes), 1)  # mesma disputa (A x C): fatias unidas
        self.assertEqual(potes[0].elegiveis, ["A", "C"])

    def test_aposta_nao_paga_vira_devolucao(self):
        potes = calcular_potes({"A": 500, "B": 200})
        self.assertEqual([p.valor for p in potes], [400, 300])
        self.assertFalse(potes[0].devolucao)
        self.assertTrue(potes[1].devolucao)
        self.assertEqual(potes[1].elegiveis, ["A"])

    def test_soma_dos_potes_igual_contribuicoes(self):
        contrib = {"A": 37, "B": 210, "C": 5, "D": 210, "E": 99}
        potes = calcular_potes(contrib, desistiram=["E"])
        self.assertEqual(sum(p.valor for p in potes), sum(contrib.values()))


class TestDistribuir(unittest.TestCase):
    def test_vencedor_unico_leva_tudo(self):
        potes = calcular_potes({"A": 100, "B": 100})
        ganhos, _ = distribuir_potes(potes, {"A": (5, (14,)), "B": (1, (2,))}, ["A", "B"])
        self.assertEqual(ganhos, {"A": 200})

    def test_empate_divide_igualmente(self):
        potes = calcular_potes({"A": 100, "B": 100, "C": 100})
        forca = (4, (9,))
        ganhos, _ = distribuir_potes(potes, {"A": forca, "B": forca, "C": (0, (13,))},
                                     ["A", "B", "C"])
        self.assertEqual(ganhos, {"A": 150, "B": 150})

    def test_ficha_impar_vai_para_primeiro_a_esquerda_do_botao(self):
        potes = calcular_potes({"A": 51, "B": 50, "C": 50}, desistiram=["A"])
        forca = (4, (9,))
        # Ordem a partir da esquerda do botão: C, A, B
        ganhos, _ = distribuir_potes(potes, {"B": forca, "C": forca}, ["C", "A", "B"])
        # A desistiu, então a ficha extra que só ele pôs entra no pote disputado
        # por B e C: 151 dividido por 2 = 75 + 1 ficha ímpar para C (primeiro na ordem).
        self.assertEqual(sum(ganhos.values()), 151)
        self.assertEqual(ganhos["C"], 76)
        self.assertEqual(ganhos["B"], 75)

    def test_empate_tres_vias_com_resto(self):
        potes = calcular_potes({"A": 100, "B": 100, "C": 100, "D": 33}, desistiram=["D"])
        forca = (2, (10, 4, 14))
        ganhos, _ = distribuir_potes(potes, {"A": forca, "B": forca, "C": forca},
                                     ["B", "C", "D", "A"])
        self.assertEqual(sum(ganhos.values()), 333)
        self.assertEqual(ganhos, {"B": 111, "C": 111, "A": 111})
        potes = calcular_potes({"A": 100, "B": 100, "C": 100, "D": 34}, desistiram=["D"])
        ganhos, _ = distribuir_potes(potes, {"A": forca, "B": forca, "C": forca},
                                     ["B", "C", "D", "A"])
        self.assertEqual(ganhos, {"B": 112, "C": 111, "A": 111})

    def test_side_pots_com_vencedores_diferentes(self):
        # A (menor stack) tem a melhor mão, B a segunda, C a pior.
        contrib = {"A": 50, "B": 150, "C": 300, "D": 300}
        forcas = {"A": (8, (9,)), "B": (6, (3, 2)), "C": (1, (2, 14, 13, 12)),
                  "D": (1, (2, 14, 13, 11))}
        potes = calcular_potes(contrib)
        ganhos, divisoes = distribuir_potes(potes, forcas, ["A", "B", "C", "D"])
        self.assertEqual(ganhos, {"A": 200, "B": 300, "C": 300})
        self.assertEqual([d.vencedores for d in divisoes], [["A"], ["B"], ["C"]])

    def test_side_pot_dividido_e_principal_unico(self):
        contrib = {"A": 50, "B": 200, "C": 200}
        forcas = {"A": (7, (14, 2)), "B": (4, (10,)), "C": (4, (10,))}
        ganhos, _ = distribuir_potes(calcular_potes(contrib), forcas, ["A", "B", "C"])
        self.assertEqual(ganhos, {"A": 150, "B": 150, "C": 150})

    def test_com_avaliador_real(self):
        mesa = cartas("Ac Kd 7h 7s 2c")
        maos = {"A": cartas("Ah 3d"), "B": cartas("As 4c"), "C": cartas("Kh Kc")}
        forcas = {j: avaliar(m + mesa) for j, m in maos.items()}
        potes = calcular_potes({"A": 100, "B": 100, "C": 40})
        ganhos, _ = distribuir_potes(potes, forcas, ["A", "B", "C"])
        # C (full house) leva o principal (120); A e B (dois pares, ases e setes,
        # kicker K) dividem o lateral de 120.
        self.assertEqual(ganhos, {"C": 120, "A": 60, "B": 60})


if __name__ == "__main__":
    unittest.main()
