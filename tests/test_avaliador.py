"""Ranking das mãos e empates."""
import itertools
import random
import unittest

from poker.avaliador import avaliar, descrever
from poker.cartas import baralho_completo, cartas


def f(txt):
    return avaliar(cartas(txt))


class TestCategorias(unittest.TestCase):
    def test_cada_categoria(self):
        casos = [
            ("Ah Kh Qh Jh Th", 8),
            ("9c 9d 9h 9s 2c", 7),
            ("Kc Kd Kh 4s 4c", 6),
            ("2h 7h 9h Jh Kh", 5),
            ("5c 6d 7h 8s 9c", 4),
            ("Qc Qd Qh 4s 2c", 3),
            ("Jc Jd 4h 4s Ac", 2),
            ("Tc Td 4h 8s Ac", 1),
            ("2c 5d 9h Js Kc", 0),
        ]
        for txt, cat in casos:
            with self.subTest(txt=txt):
                self.assertEqual(f(txt)[0], cat)

    def test_ordem_das_categorias(self):
        ordem = ["2c 5d 9h Js Kc", "Tc Td 4h 8s Ac", "Jc Jd 4h 4s Ac", "Qc Qd Qh 4s 2c",
                 "5c 6d 7h 8s 9c", "2h 7h 9h Jh Kh", "Kc Kd Kh 4s 4c", "9c 9d 9h 9s 2c",
                 "5h 6h 7h 8h 9h"]
        forcas = [f(t) for t in ordem]
        self.assertEqual(forcas, sorted(forcas))

    def test_roda_e_a_menor_sequencia(self):
        roda = f("Ac 2d 3h 4s 5c")
        self.assertEqual(roda, (4, (5,)))
        self.assertLess(roda, f("2d 3h 4s 5c 6d"))
        self.assertEqual(f("Ac Kd Qh Js Tc"), (4, (14,)))

    def test_sem_volta_na_sequencia(self):
        # Q-K-A-2-3 não é sequência
        self.assertEqual(f("Qc Kd Ah 2s 3c")[0], 0)

    def test_straight_flush_roda(self):
        self.assertEqual(f("Ah 2h 3h 4h 5h"), (8, (5,)))
        self.assertLess(f("Ah 2h 3h 4h 5h"), f("2h 3h 4h 5h 6h"))

    def test_royal(self):
        self.assertEqual(descrever(f("Ah Kh Qh Jh Th")), "Royal flush")

    def test_sete_cartas_escolhe_melhor(self):
        # Flush e sequência disponíveis: flush vence
        self.assertEqual(f("4h 5d 6h 7h 8c Kh 2h")[0], 5)
        # Straight flush escondido em 7 cartas com flush maior fora da sequência
        self.assertEqual(f("5s 6s 7s 8s 9s As Ks"), (8, (9,)))
        # Duas trincas formam full house com a maior trinca
        self.assertEqual(f("Kc Kd Kh 7s 7c 7d 2h"), (6, (13, 7)))
        # Trinca + dois pares: full com o maior par
        self.assertEqual(f("5c 5d 5h Qs Qc 9d 9h"), (6, (5, 12)))
        # Três pares: os dois maiores + melhor kicker (que pode ser do terceiro par)
        self.assertEqual(f("Ac Ad Kh Ks 9c 9d 2h"), (2, (14, 13, 9)))
        # Quadra com kicker vindo de um par
        self.assertEqual(f("8c 8d 8h 8s Qc Qd 3h"), (7, (8, 12)))
        # Sequência de 6 cartas usa a maior
        self.assertEqual(f("4c 5d 6h 7s 8c 9d Kh"), (4, (9,)))

    def test_flush_compara_todas_as_cartas(self):
        a = f("Ah Jh 9h 6h 3h")
        b = f("Ad Jd 9d 6d 2d")
        self.assertGreater(a, b)


class TestEmpatesEKickers(unittest.TestCase):
    def test_kicker_decide_par(self):
        self.assertGreater(f("Ac Ad Kh 7s 2c"), f("Ah As Qh 7d 2d"))

    def test_kicker_decide_dois_pares(self):
        self.assertGreater(f("Jc Jd 4h 4s Ac"), f("Jh Js 4c 4d Kc"))

    def test_segundo_par_decide(self):
        self.assertGreater(f("Jc Jd 5h 5s 2c"), f("Jh Js 4c 4d Ac"))

    def test_empate_exato_naipes_diferentes(self):
        self.assertEqual(f("Ac Kd Qh 9s 7c"), f("Ad Kh Qc 9d 7h"))

    def test_mesa_joga_empate(self):
        # Sequência na mesa; nenhuma carta própria melhora
        mesa = "5c 6d 7h 8s 9c"
        self.assertEqual(f("2d 2h " + mesa), f("3s Ac " + mesa))

    def test_kicker_alem_da_quinta_carta_nao_conta(self):
        mesa = "Ac Ad Kh Qs Jc"
        # Ambos jogam A A K Q J; o 9 e o 8 não entram nas 5 melhores
        self.assertEqual(f("9d 2h " + mesa), f("8s 3c " + mesa))

    def test_kicker_de_quadra_na_mesa(self):
        mesa = "7c 7d 7h 7s 2c"
        self.assertGreater(f("Ah 3d " + mesa), f("Kh Qd " + mesa))
        self.assertEqual(f("3h 4d " + mesa), f("4h 3c " + mesa))

    def test_full_house_compara_trinca_primeiro(self):
        self.assertGreater(f("3c 3d 3h 2s 2c"), f("2d 2h 2s Ac Ad"))


class TestConsistencia(unittest.TestCase):
    def test_sete_cartas_igual_melhor_combinacao_de_cinco(self):
        """Confere a avaliação direta de 7 cartas contra a força bruta (21 combinações)."""
        rng = random.Random(7)
        baralho = baralho_completo()
        for _ in range(3000):
            mao = rng.sample(baralho, 7)
            esperado = max(avaliar(list(c)) for c in itertools.combinations(mao, 5))
            self.assertEqual(avaliar(mao), esperado, msg=str([str(c) for c in mao]))


if __name__ == "__main__":
    unittest.main()
