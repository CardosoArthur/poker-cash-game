"""Estatísticas (VPIP, PFR, 3-bet, WTSD...), histórico em texto e formato PokerStars."""
import os
import unittest

from poker.acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao
from poker.estatisticas import EstatMao, diagnostico, resumir, resumir_por_posicao
from poker.historico import HistoricoPokerStars, HistoricoTexto, descrever_en, nome_ps
from poker.avaliador import avaliar
from poker.cartas import cartas
from tests.auxiliares import PastaTemporaria, Roteiro, SempreAllIn, baralho_com, mesa_com


class TestRastreador(unittest.TestCase):
    def test_vpip_pfr_3bet_wtsd(self):
        # A (botão) abre para 30, B (SB) dá 3-bet para 90, C (BB) desiste, A paga.
        # Flop: B aposta, A paga; turn e river passam -> showdown.
        a = Roteiro([Acao(AUMENTAR, 30), Acao(PAGAR), Acao(PAGAR)])
        b = Roteiro([Acao(AUMENTAR, 90), Acao(AUMENTAR, 50)])
        c = Roteiro([Acao(DESISTIR)])
        mesa = mesa_com([1000, 1000, 1000], [a, b, c])
        mesa.jogar_mao(baralho_com("2h 3d Ah 7c 8d Ad 4c Ks Qs 9h 5c Jd 6c 2s"))
        r = mesa.rastreador.por_jogador
        ea, eb, ec = r["A"][0], r["B"][0], r["C"][0]
        self.assertTrue(ea.vpip and ea.pfr and ea.oport_3bet is False and ea.viu_flop and ea.showdown)
        self.assertTrue(eb.vpip and eb.pfr and eb.oport_3bet and eb.fez_3bet)
        self.assertFalse(ec.vpip or ec.viu_flop)
        self.assertTrue(ea.ganhou_showdown)          # A tem par de ases
        self.assertFalse(eb.ganhou_showdown)
        self.assertEqual(eb.agressoes_pos, 1)
        self.assertEqual(ea.pagamentos_pos, 1)
        self.assertEqual(ea.resultado + eb.resultado + ec.resultado, 0)

    def test_resumo_e_bb100(self):
        maos = [EstatMao("V", "BTN", 10, vpip=True, pfr=True, resultado=50),
                EstatMao("V", "BB", 10, resultado=-10),
                EstatMao("V", "BTN", 10, vpip=True, viu_flop=True, showdown=True, ganhou_showdown=True,
                         resultado=40, agressoes_pos=2, pagamentos_pos=1)]
        r = resumir(maos)
        self.assertEqual(r["maos"], 3)
        self.assertAlmostEqual(r["vpip"], 200 / 3)
        self.assertAlmostEqual(r["pfr"], 100 / 3)
        self.assertEqual(r["wtsd"], 100.0)
        self.assertEqual(r["af"], 2.0)
        self.assertAlmostEqual(r["bb100"], 8 / 3 * 100)
        self.assertEqual(set(resumir_por_posicao(maos)), {"BTN", "BB"})
        self.assertTrue(diagnostico(r))  # com poucas mãos pede mais amostra


class TestHistoricos(unittest.TestCase):
    def test_descricoes_em_ingles(self):
        f = lambda t: descrever_en(avaliar(cartas(t)))  # noqa: E731
        self.assertEqual(f("Ah Kh Qh Jh Th"), "a Royal Flush")
        self.assertEqual(f("Ac 2d 3h 4s 5c"), "a straight, Ace to Five")
        self.assertEqual(f("Kc Kd Kh 7s 7c"), "a full house, Kings full of Sevens")
        self.assertEqual(f("Ac Ad 7h 7s 2c"), "two pair, Aces and Sevens")
        self.assertEqual(f("2c 5d 9h Js Kc"), "high card King")
        self.assertEqual(nome_ps("Você Íris"), "Voce_Iris")

    def test_pokerstars_side_pots_e_devolucao(self):
        with PastaTemporaria() as pasta:
            ps = os.path.join(pasta, "h_ps.txt")
            pt = os.path.join(pasta, "h_pt.txt")
            # A 1000 (botão), B 300, C 100 — todos all-in; A tem a melhor mão.
            mesa = mesa_com([1000, 300, 100], [SempreAllIn()] * 3, humano=0,
                            ouvintes=[HistoricoPokerStars(ps, id_base=7000), HistoricoTexto(pt)])
            mesa.assentos[0].estrategia = None
            mesa.decisor_humano = lambda j, e, op: Acao(ALL_IN)
            mesa.jogar_mao(baralho_com("Kh Qh Ah Kd Qd Ad 3c 2c 7s 9d 5h Jc 6h 4s"))
            with open(ps, encoding="utf-8") as f:
                texto = f.read()
            for trecho in ["PokerStars Hand #7001:", "Hold'em No Limit (5/10)", "Seat #1 is the button",
                           "Seat 1: A (1000 in chips)", "B: posts small blind 5", "C: posts big blind 10",
                           "*** HOLE CARDS ***", "Dealt to A [Ah Ad]", "*** FLOP *** [2c 7s 9d]",
                           "*** TURN *** [2c 7s 9d] [Jc]", "*** RIVER *** [2c 7s 9d Jc] [4s]",
                           "*** SHOW DOWN ***", "A: shows [Ah Ad]", "Uncalled bet (700) returned to A",
                           "A collected 300 from main pot", "A collected 400 from side pot",
                           "Total pot 700 Main pot 300. Side pot 400. | Rake 0", "Board [2c 7s 9d Jc 4s]",
                           "Seat 1: A (button) showed [Ah Ad] and won (700)"]:
                self.assertIn(trecho, texto)
            with open(pt, encoding="utf-8") as f:
                self.assertIn("700 devolvido a A", f.read())


if __name__ == "__main__":
    unittest.main()
