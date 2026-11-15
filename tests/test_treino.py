"""Ranges, quiz, treinador, cenários e bots."""
import random
import unittest

from poker.acoes import AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao, EstadoMao, Opcoes
from poker.cartas import cartas
from poker.cenarios import CENARIOS, jogar_cenario, por_id
from poker.config import Configuracao
from poker.mesa import Mesa
from poker.quiz import corrigir, gerar_pergunta
from poker.ranges import (ABERTURA, ORDEM, classe_mao, combos, grade, nomes_posicoes, percentil,
                          range_top, tabela_posicao)
from poker.treinador import ALERTA, OK, comentar
from tests.auxiliares import sempre_paga


class TestRanges(unittest.TestCase):
    def test_169_classes_e_1326_combinacoes(self):
        self.assertEqual(len(ORDEM), 169)
        self.assertEqual(len(set(ORDEM)), 169)
        self.assertEqual(sum(combos(c) for c in ORDEM), 1326)
        self.assertEqual(ORDEM[0], "AA")
        self.assertEqual(ORDEM[-1], "72o")

    def test_classe_e_percentil(self):
        a, k = cartas("Ah Kh")
        self.assertEqual(classe_mao(a, k), "AKs")
        self.assertEqual(classe_mao(*cartas("2c 7d")), "72o")
        self.assertEqual(classe_mao(*cartas("9c 9d")), "99")
        self.assertEqual(percentil("AA"), 0)
        self.assertLess(percentil("AKs"), percentil("T9s"))

    def test_ranges_crescem_com_a_posicao(self):
        tamanhos = [len(range_top(ABERTURA[p])) for p in ["UTG", "MP", "HJ", "CO", "BTN"]]
        self.assertEqual(tamanhos, sorted(tamanhos))
        self.assertTrue(range_top(ABERTURA["UTG"]) <= range_top(ABERTURA["BTN"]))

    def test_grade(self):
        g = grade({"AA", "AKs", "AKo"}).splitlines()
        self.assertEqual(len(g), 14)
        self.assertIn("Abertura no botão", tabela_posicao("BTN"))

    def test_nomes_posicoes(self):
        for n in range(2, 10):
            self.assertEqual(len(nomes_posicoes(n)), n)
            self.assertEqual(len(set(nomes_posicoes(n))), n)


class TestQuiz(unittest.TestCase):
    def test_perguntas_corrigidas_pelo_range(self):
        rng = random.Random(1)
        for _ in range(200):
            p = gerar_pergunta(rng)
            self.assertEqual(corrigir(p, "a"), p.abrir)
            self.assertEqual(corrigir(p, "d"), not p.abrir)
            self.assertIn(p.classe, p.explicacao())


def _estado(rodada="Pré-flop", posicao="UTG", aumentos=0, comunitarias="", pote=15, oponentes=5):
    return EstadoMao(1, rodada, cartas(comunitarias) if comunitarias else [], pote, 10, oponentes,
                     posicao=posicao, aumentos=aumentos)


def _op(para_pagar=10, pode_passar=False):
    return Opcoes(pode_passar, para_pagar, True, 20, 1000, 10, 0)


class TestTreinador(unittest.TestCase):
    def test_preflop(self):
        rng = random.Random(1)
        self.assertEqual(comentar(cartas("Ah Ad"), _estado(), _op(), Acao(DESISTIR), rng).nivel, ALERTA)
        self.assertEqual(comentar(cartas("Ah Ad"), _estado(), _op(), Acao(AUMENTAR, 25), rng).nivel, OK)
        self.assertEqual(comentar(cartas("7c 2d"), _estado(), _op(), Acao(AUMENTAR, 25), rng).nivel, ALERTA)
        self.assertEqual(comentar(cartas("7c 2d"), _estado(), _op(), Acao(DESISTIR), rng).nivel, OK)
        self.assertEqual(comentar(cartas("Kd Qd"), _estado(), _op(), Acao(PAGAR), rng).nivel, ALERTA)  # limp
        bb = _estado(posicao="BB")
        self.assertEqual(comentar(cartas("7c 2d"), bb, _op(0, True), Acao(DESISTIR), rng).nivel, ALERTA)

    def test_posflop_pot_odds(self):
        rng = random.Random(2)
        # Nuts no river pagando aposta pequena: correto
        est = _estado("River", "BTN", 1, "Ah Kh Qh 2c 3d", pote=100, oponentes=1)
        c = comentar(cartas("Jh Th"), est, _op(50), Acao(PAGAR), rng)
        self.assertEqual(c.nivel, OK)
        self.assertGreater(c.equity, 0.99)
        # Carta alta sem chances pagando aposta grande no river: erro
        est = _estado("River", "BTN", 1, "Ah Kh Qh 9c 8d", pote=100, oponentes=1)
        self.assertEqual(comentar(cartas("3s 2d"), est, _op(200), Acao(PAGAR), rng).nivel, ALERTA)
        # Desistir dos nuts: erro
        est = _estado("River", "BTN", 1, "Ah Kh Qh 2c 3d", pote=100, oponentes=1)
        self.assertEqual(comentar(cartas("Jh Th"), est, _op(50), Acao(DESISTIR), rng).nivel, ALERTA)


class TestCenarios(unittest.TestCase):
    def test_todos_os_cenarios_rodam_e_conservam_fichas(self):
        for c in CENARIOS:
            with self.subTest(c.id):
                mesa, res = jogar_cenario(c, sempre_paga, rng=random.Random(1))
                self.assertTrue(res.ok)
                self.assertEqual(mesa.total_fichas(), sum(j[1] for j in c.jogadores))
                voce = mesa.humano
                self.assertEqual([str(x) for x in voce.cartas],
                                 [str(x) for x in cartas(next(j[2] for j in c.jogadores if j[3] is None))])
                self.assertEqual(len(mesa.comunitarias), 5)

    def test_side_pots_do_cenario(self):
        mesa, res = jogar_cenario(por_id("side_pots"), sempre_paga, rng=random.Random(1))
        fichas = {j.nome: j.fichas for j in mesa.sentados()}
        self.assertEqual(fichas, {"Você": 2440, "Ana": 0, "Bruno": 0, "Carla": 480})


class TestBots(unittest.TestCase):
    def test_dificuldades_jogam_sem_erro_e_perfis_razoaveis(self):
        for dif in ("facil", "medio", "dificil"):
            with self.subTest(dif):
                mesa = Mesa(Configuracao(num_bots=5, dificuldade=dif), random.Random(7))
                for _ in range(80):
                    self.assertTrue(mesa.jogar_mao().ok)
                    mesa.repor_bots_quebrados()
                if dif != "facil":
                    vpips = [p["vpip"] for p in mesa.rastreador.perfis().values() if p["maos"] >= 40]
                    self.assertTrue(vpips)
                    self.assertTrue(all(8 <= v <= 55 for v in vpips), vpips)

    def test_bot_dificil_se_adapta_ao_perfil(self):
        from poker.bots import EstrategiaBot
        bot = EstrategiaBot(random.Random(1), "equilibrado", "dificil")
        from poker.acoes import InfoJogador
        info = InfoJogador("X", 1000, 30, False, False, False, "CO")
        perfil_solto = {"maos": 100, "pfr": 50.0, "vpip": 60.0, "af": 4.0}
        perfil_apertado = {"maos": 100, "pfr": 5.0, "vpip": 8.0, "af": 0.5}
        est = EstadoMao(1, "Flop", [], 60, 10, 1, [info], posicao="BB", entrou_preflop={"X": "aumentou"},
                        perfis={"X": perfil_solto})
        self.assertEqual(bot._range_oponente(est, info), 50.0)
        est.perfis = {"X": perfil_apertado}
        self.assertEqual(bot._range_oponente(est, info), 5.0)


if __name__ == "__main__":
    unittest.main()
