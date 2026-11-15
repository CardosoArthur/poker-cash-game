"""Testes de propriedade: milhares de situações aleatórias de potes e mãos.

Comparam a implementação com uma referência simples (divisão fracionária por
fatia de contribuição) e verificam invariantes que precisam valer sempre.
"""
import random
import unittest
from fractions import Fraction

from poker.avaliador import avaliar
from poker.cartas import Baralho, baralho_completo
from poker.potes import calcular_potes, distribuir_potes
from tests.auxiliares import Roteiro, SempreAllIn, mesa_com


def referencia(contrib, desistiram, forcas):
    """Prêmio 'justo' de cada jogador, em frações (sem a regra da ficha ímpar)."""
    niveis = sorted({v for v in contrib.values() if v > 0})
    premio = {j: Fraction(0) for j in contrib}
    sobra = Fraction(0)
    anterior = 0
    for nivel in niveis:
        part = [j for j, v in contrib.items() if v >= nivel]
        valor = Fraction((nivel - anterior) * len(part)) + sobra
        sobra = Fraction(0)
        eleg = [j for j in part if j not in desistiram]
        anterior = nivel
        if not eleg:
            # fatia só de desistentes: vai para quem disputa a fatia anterior
            sobra = valor
            continue
        melhor = max(forcas[j] for j in eleg)
        venc = [j for j in eleg if forcas[j] == melhor]
        for j in venc:
            premio[j] += valor / len(venc)
    if sobra:  # sobra no topo: devolve à fatia anterior (mesma regra do código)
        raise AssertionError("situação não esperada no gerador")
    return premio


class TestPropriedadesPotes(unittest.TestCase):
    def test_milhares_de_situacoes_aleatorias(self):
        rng = random.Random(2026)
        baralho = baralho_completo()
        for caso in range(4000):
            n = rng.randint(2, 9)
            jogadores = [f"J{i}" for i in range(n)]
            contrib = {j: rng.choice([0, rng.randint(1, 50), rng.randint(1, 500), 500]) for j in jogadores}
            if sum(1 for v in contrib.values() if v > 0) < 2:
                continue
            ativos = [j for j in jogadores if contrib[j] > 0]
            # quem desiste nunca é o que mais contribuiu (no jogo real isso não acontece)
            maior = max(ativos, key=lambda j: contrib[j])
            desistiram = {j for j in ativos if j != maior and rng.random() < 0.3}
            cartas = rng.sample(baralho, 5 + 2 * n)
            mesa = cartas[:5]
            forcas = {j: avaliar(cartas[5 + 2 * i: 7 + 2 * i] + mesa) for i, j in enumerate(jogadores)}
            if rng.random() < 0.2:  # força empates frequentes
                f = forcas[maior]
                for j in jogadores:
                    if rng.random() < 0.5:
                        forcas[j] = f

            potes = calcular_potes(contrib, desistiram)
            ganhos, divisoes = distribuir_potes(potes, forcas, jogadores)
            total = sum(contrib.values())

            # 1. conservação: tudo o que entrou sai
            self.assertEqual(sum(p.valor for p in potes), total)
            self.assertEqual(sum(ganhos.values()), total)
            # 2. desistentes nunca recebem
            for j in desistiram:
                self.assertNotIn(j, ganhos)
            # 3. ninguém ganha mais do que cobriu de cada adversário
            for j, g in ganhos.items():
                cobre = sum(min(contrib[j], contrib[k]) for k in jogadores)
                self.assertLessEqual(g, cobre, msg=f"caso {caso}")
            # 4. igual à referência a menos das fichas ímpares (< 1 ficha por pote)
            ref = referencia(contrib, desistiram, forcas)
            for j in jogadores:
                self.assertLess(abs(ganhos.get(j, 0) - ref[j]), len(potes) + 1, msg=f"caso {caso}")
            # 5. todo pote tem ao menos um elegível que não desistiu
            for p in potes:
                self.assertTrue(p.elegiveis)
                self.assertTrue(all(j not in desistiram for j in p.elegiveis))


class TestPropriedadesMesa(unittest.TestCase):
    def test_maos_aleatorias_com_ante_e_straddle(self):
        rng = random.Random(11)
        for _ in range(250):
            n = rng.randint(2, 9)
            stacks = [rng.randint(1, 300) for _ in range(n)]
            estrategias = [SempreAllIn() if rng.random() < 0.4 else Roteiro([]) for _ in range(n)]
            ante = rng.choice([0, 0, 1, 2])
            mesa = mesa_com(stacks, estrategias, sb=2, bb=4, ante=ante, straddle=rng.random() < 0.3)
            total = sum(stacks)
            for _ in range(4):
                res = mesa.jogar_mao(Baralho(rng))
                if res is None:
                    break
                self.assertEqual(mesa.total_fichas(), total)
                self.assertTrue(all(j.fichas >= 0 for j in mesa.sentados()))


if __name__ == "__main__":
    unittest.main()
