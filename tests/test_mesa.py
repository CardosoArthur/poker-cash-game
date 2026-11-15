"""Mãos completas no motor da mesa: side pots, devolução, conservação de fichas."""
import random
import unittest

from poker.acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao
from poker.cartas import Baralho
from poker.config import Configuracao
from poker.mesa import Mesa
from tests.auxiliares import Roteiro, SempreAllIn, baralho_com, mesa_com


class TestMaosRoteirizadas(unittest.TestCase):
    def test_side_pots_tres_all_ins(self):
        # Assentos: A(botão)=100, B(SB)=300, C(BB)=500. Ordem de distribuição: B, C, A.
        mesa = mesa_com([100, 300, 500], [SempreAllIn(), SempreAllIn(), SempreAllIn()])
        baralho = baralho_com(
            "Kh Qh Ah Kd Qd Ad "      # B: Kh Kd | C: Qh Qd | A: Ah Ad
            "3c 2c 7s 9d 5h Jc 6h 4s"  # queima, flop, queima, turn, queima, river
        )
        res = mesa.jogar_mao(baralho)
        a, b, c = mesa.sentados()
        self.assertEqual((a.fichas, b.fichas, c.fichas), (300, 400, 200))
        self.assertTrue(res.ok)
        self.assertEqual(mesa.total_fichas(), 900)

    def test_aposta_nao_paga_volta(self):
        # A (botão) 1000, B (SB) 1000, C (BB) 200. A vai all-in, B desiste, C paga all-in.
        mesa = mesa_com([1000, 1000, 200],
                        [Roteiro([Acao(ALL_IN)]), Roteiro([Acao(DESISTIR)]), Roteiro([Acao(PAGAR)])])
        baralho = baralho_com("2h 3d Ah 7c 8d Ad 4c Ks Qs 9h 5c Jd 6c 2s")
        mesa.jogar_mao(baralho)
        a, b, c = mesa.sentados()
        # Pote disputado: 200 (A) + 5 (B) + 200 (C) = 405 para A; os 800 que
        # ninguém pagou voltam para A. A termina com 405 + 800 = 1205.
        self.assertEqual(b.fichas, 995)
        self.assertEqual(c.fichas, 0)
        self.assertEqual(a.fichas, 1205)

    def test_empate_divide_pote_na_mesa(self):
        # Sequência na mesa (5-9) -> todos que chegam ao showdown dividem.
        mesa = mesa_com([1000, 1000, 1000],
                        [Roteiro([]), Roteiro([]), Roteiro([])])
        baralho = baralho_com("2h 3d 2c 3h 2d 4c Ks 5c 6d 7h Kd 8s Qc 9c")
        mesa.jogar_mao(baralho)
        self.assertEqual([j.fichas for j in mesa.sentados()], [1000, 1000, 1000])

    def test_empate_com_ficha_impar(self):
        # Botão (A) paga 10, SB (B) desiste deixando 5, BB (C) passa.
        # Pote 25 dividido entre A e C (empate) -> 12 + 13, a ficha ímpar vai
        # para o primeiro à esquerda do botão (C, o big blind).
        mesa = mesa_com([1000, 1000, 1000],
                        [Roteiro([Acao(PAGAR)]), Roteiro([Acao(DESISTIR)]), Roteiro([])])
        baralho = baralho_com("2h 3d 2c 3h 2d 4c Ks 5c 6d 7h Kd 8s Qc 9c")
        mesa.jogar_mao(baralho)
        a, b, c = mesa.sentados()
        self.assertEqual(b.fichas, 995)
        self.assertEqual(a.fichas - 1000 + c.fichas - 1000, 5)
        self.assertEqual(c.fichas, 1003)
        self.assertEqual(a.fichas, 1002)

    def test_all_in_curto_nao_reabre_aumento(self):
        # A aposta 100 no pré-flop; B (stack 130) vai all-in (aumento de 30 < mínimo 90);
        # C paga. A só pode pagar ou desistir.
        a_rot = Roteiro([Acao(AUMENTAR, 100), Acao(AUMENTAR, 500)])
        mesa = mesa_com([1000, 130, 1000], [a_rot, Roteiro([Acao(ALL_IN)]), Roteiro([Acao(PAGAR)])])
        vistos = []
        original = mesa.opcoes

        def espiar(j):
            op = original(j)
            if j.nome == "A":
                vistos.append(op.pode_aumentar)
            return op
        mesa.opcoes = espiar
        mesa.jogar_mao(baralho_com("2h 3d 4c 5h 6d 8c Ks Qs 9h 7c Jd Tc 2s Ac"))
        self.assertIn(False, vistos)
        self.assertEqual(mesa.total_fichas(), 2130)


class TestConservacao(unittest.TestCase):
    def test_muitas_maos_com_bots(self):
        for semente in range(4):
            rng = random.Random(semente)
            cfg = Configuracao(fichas_iniciais=rng.choice([200, 500, 1000]),
                               num_bots=rng.randint(2, 8))
            mesa = Mesa(cfg, rng)
            for _ in range(60):
                res = mesa.jogar_mao()  # lança ErroConservacao se não bater
                self.assertTrue(res.ok)
                mesa.repor_bots_quebrados()
                self.assertEqual(mesa.total_fichas(), mesa.total_esperado())

    def test_stacks_desiguais_e_all_ins_em_massa(self):
        rng = random.Random(42)
        for _ in range(150):
            n = rng.randint(2, 9)
            stacks = [rng.randint(1, 400) for _ in range(n)]
            estrategias = [SempreAllIn() if rng.random() < 0.6 else Roteiro([]) for _ in range(n)]
            mesa = mesa_com(stacks, estrategias, sb=2, bb=4)
            total = sum(stacks)
            for _ in range(5):
                res = mesa.jogar_mao(Baralho(rng))
                if res is None:
                    break
                self.assertEqual(mesa.total_fichas(), total)


class TestAnteStraddle(unittest.TestCase):
    def test_ante_vai_para_o_pote_e_nao_conta_como_aposta(self):
        eventos = []
        mesa = mesa_com([1000, 1000, 1000], [Roteiro([Acao(DESISTIR)]), Roteiro([Acao(DESISTIR)]), Roteiro([])],
                        ante=2, ouvintes=[eventos.append])
        mesa.jogar_mao(baralho_com("2h 3d 4c 5h 6d 8c Ks Qs 9h 7c Jd Tc 2s Ac"))
        a, b, c = mesa.sentados()
        # A e B desistem; C (BB) leva antes (6) + SB (5) e recebe de volta a sua parte.
        self.assertEqual((a.fichas, b.fichas, c.fichas), (998, 993, 1009))
        antes = [e for e in eventos if e["tipo"] == "ante"]
        self.assertEqual(len(antes), 3)

    def test_ante_all_in_cria_pote_so_de_antes(self):
        mesa = mesa_com([2, 1000, 1000], [Roteiro([]), Roteiro([]), Roteiro([])], ante=2)
        # A (2 fichas, botão) fica all-in só com o ante e tem a melhor mão.
        mesa.jogar_mao(baralho_com("2h 3d Ah 7c 8d Ad 4c Ks Qs 9h 5c Jd 6c 2s"))
        a, b, c = mesa.sentados()
        self.assertEqual(a.fichas, 6)  # ganha só o pote dos antes (2 x 3)
        self.assertEqual(mesa.total_fichas(), 2002)

    def test_straddle_age_por_ultimo_e_define_aumento_minimo(self):
        eventos = []
        # 4 jogadores: A botão, B SB, C BB, D straddle (20). A age primeiro.
        mesa = mesa_com([1000] * 4, [Roteiro([]), Roteiro([]), Roteiro([]), Roteiro([])],
                        straddle=True, ouvintes=[eventos.append])
        vistos = []
        original = mesa.opcoes

        def espiar(j):
            op = original(j)
            vistos.append((j.nome, op.para_pagar, op.min_para))
            return op
        mesa.opcoes = espiar
        mesa.jogar_mao(baralho_com("2h 3d 4c 5h 6d 8c Ks Qs 9h 7c Jd Tc 2s Ac As Ad"))
        blinds = [(e["nome"], e["blind"], e["valor"]) for e in eventos if e["tipo"] == "blind"]
        self.assertEqual(blinds, [("B", "small blind", 5), ("C", "big blind", 10), ("D", "straddle", 20)])
        acoes_pre = [e["nome"] for e in eventos if e["tipo"] == "acao" and e["rodada"] == "Pré-flop"]
        self.assertEqual(acoes_pre, ["A", "B", "C", "D"])
        self.assertEqual(vistos[0][1:], (20, 40))  # A paga 20; aumento mínimo para 40
        self.assertEqual(mesa.total_fichas(), 4000)

    def test_posicoes_6_jogadores(self):
        eventos = []
        mesa = mesa_com([1000] * 6, [Roteiro([]) for _ in range(6)], ouvintes=[eventos.append])
        mesa.jogar_mao()
        pos = next(e for e in eventos if e["tipo"] == "inicio_mao")["posicoes"]
        self.assertEqual(pos, {"A": "BTN", "B": "SB", "C": "BB", "D": "UTG", "E": "HJ", "F": "CO"})


class TestSalvarRestaurar(unittest.TestCase):
    def test_mesa_restaurada_continua_igual(self):
        rng = random.Random(3)
        mesa = Mesa(Configuracao(num_bots=4), rng)
        for _ in range(10):
            mesa.jogar_mao()
            mesa.repor_bots_quebrados()
        d = mesa.para_dict()
        nova = Mesa.de_dict(d, random.Random(4))
        self.assertEqual([(j.nome, j.fichas) for j in nova.sentados()],
                         [(j.nome, j.fichas) for j in mesa.sentados()])
        self.assertEqual((nova.botao, nova.num_mao, nova.total_esperado()),
                         (mesa.botao, mesa.num_mao, mesa.total_esperado()))
        for _ in range(10):
            res = nova.jogar_mao()
            self.assertTrue(res.ok)
            nova.repor_bots_quebrados()


if __name__ == "__main__":
    unittest.main()
