"""Cenários de prática: situações fixas (cartas, stacks e ações dos oponentes
definidas) para treinar decisões específicas. Depois da mão o jogo mostra a
análise do cenário.

Os oponentes seguem um roteiro por rodada; quando o roteiro acaba (ou se você
fizer algo diferente do esperado), passam a jogar como bot difícil.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao
from .bots import EstrategiaBot
from .cartas import Baralho, baralho_completo, cartas
from .config import MAX_ASSENTOS, Configuracao
from .mesa import Jogador, Mesa


class RoteiroPorRodada:
    """Executa ações pré-definidas por rodada; depois, joga como bot."""

    def __init__(self, roteiro: Dict[str, List[Acao]], reserva: EstrategiaBot):
        self.roteiro = {k: list(v) for k, v in roteiro.items()}
        self.reserva = reserva
        self.estilo = "roteiro"

    def decidir(self, minhas, estado, op):
        fila = self.roteiro.get(estado.rodada)
        if fila:
            return fila.pop(0)
        return self.reserva.decidir(minhas, estado, op)


@dataclass
class Cenario:
    id: str
    titulo: str
    descricao: str
    analise: str
    # (nome, fichas, cartas "Ah Kh", roteiro) — roteiro None = você
    jogadores: List[Tuple[str, int, str, Optional[Dict[str, List[Acao]]]]]
    botao: int                      # índice (assento) do botão
    mesa: str                       # 5 cartas comunitárias
    small_blind: int = 5
    big_blind: int = 10
    ante: int = 0


def montar_baralho(c: Cenario) -> Baralho:
    """Ordena o baralho para que cada jogador receba as cartas do cenário."""
    n = len(c.jogadores)
    ordem_assentos = [(c.botao + 1 + i) % n for i in range(n)]
    maos = {i: cartas(j[2]) for i, j in enumerate(c.jogadores)}
    board = cartas(c.mesa)
    usadas = set(board) | {x for m in maos.values() for x in m}
    queimar = [x for x in baralho_completo() if x not in usadas]
    seq = []
    for r in range(2):
        for i in ordem_assentos:
            seq.append(maos[i][r])
    seq += [queimar[0]] + board[:3] + [queimar[1], board[3], queimar[2], board[4]]
    resto = [x for x in baralho_completo() if x not in set(seq)]
    return Baralho(ordem_fixa=seq + resto)


def preparar_mesa(c: Cenario, decisor_humano, observador=None, ouvintes=None,
                  rng: Optional[random.Random] = None) -> Mesa:
    rng = rng or random.Random()
    cfg = Configuracao(fichas_iniciais=max(j[1] for j in c.jogadores), num_bots=len(c.jogadores) - 1,
                       small_blind=c.small_blind, big_blind=c.big_blind, ante=c.ante,
                       repor_bots=False, dificuldade="dificil", treinador=True)
    jogadores = []
    for nome, fichas, _, roteiro in c.jogadores:
        if roteiro is None:
            jogadores.append(Jogador(nome, fichas, humano=True))
        else:
            reserva = EstrategiaBot(random.Random(rng.random()), "equilibrado", "dificil")
            jogadores.append(Jogador(nome, fichas, estrategia=RoteiroPorRodada(roteiro, reserva)))
    mesa = Mesa(cfg, rng, decisor_humano=decisor_humano, observador=observador,
                jogadores=jogadores, ouvintes=ouvintes)
    mesa.botao = (c.botao - 1) % MAX_ASSENTOS if c.botao > 0 else MAX_ASSENTOS - 1
    return mesa


def jogar_cenario(c: Cenario, decisor_humano, observador=None, ouvintes=None, rng=None):
    mesa = preparar_mesa(c, decisor_humano, observador, ouvintes, rng)
    resultado = mesa.jogar_mao(montar_baralho(c))
    return mesa, resultado


A = lambda para: Acao(AUMENTAR, para)  # noqa: E731

CENARIOS: List[Cenario] = [
    Cenario(
        id="flush_draw",
        titulo="Flush draw no flop",
        descricao=("Heads-up, você está no botão com 1000 fichas. Bruno (big blind) paga seu aumento e "
                   "aposta no flop e no turn. Você tem o flush draw do ás."),
        analise=("Com A♥T♥ num flop K♥7♥2♣ você tem 9 outs de flush (mais o ás como possível carta boa): "
                 "cerca de 35–40% de equity contra um par de reis até o river. Uma aposta de 60 num pote "
                 "de ~60 oferece pot odds de 33%: pagar é lucrativo, e aumentar como semi-blefe também é "
                 "uma boa opção, porque você pode ganhar o pote na hora ou completar o flush. No turn, "
                 "com uma carta a menos para vir, a equity cai para ~20%: pagar uma aposta grande só faz "
                 "sentido pelas odds implícitas (o quanto você ganha se o flush vier). Bruno tinha K♣Q♦."),
        jogadores=[("Você", 1000, "Ah Th", None),
                   ("Bruno", 1000, "Kc Qd", {"Pré-flop": [Acao(PAGAR)], "Flop": [A(60)],
                                              "Turn": [A(150)], "River": [Acao(PASSAR)]})],
        botao=0, mesa="Kh 7h 2c 4s 9h"),
    Cenario(
        id="river_pagar",
        titulo="River: pagar ou desistir?",
        descricao=("Você está no big blind com K♦J♣. Carla (botão) aumenta, aposta no flop e no turn e "
                   "faz uma aposta grande no river. Você tem top pair com bom kicker."),
        analise=("Uma mão como top pair com bom kicker no river é um 'bluff catcher': ganha de todos os "
                 "blefes e perde para quase todas as apostas por valor. A decisão vem das pot odds: "
                 "pagar 250 num pote final de ~650 exige ganhar ~38% das vezes. Draws que não fecharam "
                 "(como 9♠T♠, que tinha sequência aberta e flush de espadas) explicam muitas apostas "
                 "grandes no river. Neste caso Carla blefava, então pagar era o certo — mas contra "
                 "jogadores que quase nunca blefam, desistir pode ser melhor."),
        jogadores=[("Carla", 1000, "9s Ts", {"Pré-flop": [A(25)], "Flop": [A(30)],
                                               "Turn": [A(80)], "River": [A(250)]}),
                   ("Você", 1000, "Kd Jc", None)],
        botao=0, mesa="Jh 8s 3c 2d 5s"),
    Cenario(
        id="side_pots",
        titulo="All-ins múltiplos e side pots",
        descricao=("Mesa de 4. Carla (cutoff, 120 fichas) vai all-in, você está no botão com Q♥Q♠ e 1500 "
                   "fichas. Depois Ana (SB, 300) e Bruno (BB, 1000) também vão all-in."),
        analise=("Com stacks diferentes, cada all-in cria um pote separado. O pote principal "
                 "(120 de cada um dos 4 = 480) pode ser ganho por qualquer jogador; o lateral 1 "
                 "((300−120) × 3 = 540) só por quem tem 300 ou mais; o lateral 2 ((1000−300) × 2 = 1400) "
                 "só por você e Bruno. Aqui Carla ganha o principal com A♦K♣ (par de ases), mas sua "
                 "dama alta vence os laterais contra 7♣7♦ e J♥J♠. Damas são fortes o bastante para "
                 "pagar contra três all-ins de stacks curtos e médios."),
        jogadores=[("Você", 1500, "Qh Qs", None),
                   ("Ana", 300, "7c 7d", {"Pré-flop": [Acao(ALL_IN)]}),
                   ("Bruno", 1000, "Jh Js", {"Pré-flop": [Acao(ALL_IN)]}),
                   ("Carla", 120, "Ad Kc", {"Pré-flop": [Acao(ALL_IN)]})],
        botao=0, mesa="Ac 9s 4h 2c 8d"),
    Cenario(
        id="set_molhado",
        titulo="Trinca num flop perigoso",
        descricao=("Três jogadores. Diego (botão) aumenta, Elisa (SB) desiste e você paga no big blind com "
                   "6♣6♦. O flop vem 6♥7♥8♣: você fez trinca, mas o board tem sequências e flush possíveis."),
        analise=("Trinca em board 'molhado' é forte, mas vulnerável: draws de flush e sequência têm "
                 "muitas outs. Apostar (ou aumentar a continuation bet do oponente) cobra caro dos draws "
                 "e protege sua mão; passar e só pagar dá cartas grátis. Diego tinha A♥K♥ — flush draw "
                 "do ás com ~25–30% de equity. Apostas de 2/3 a pote inteiro são o padrão aqui."),
        jogadores=[("Diego", 1000, "Ah Kh", {"Pré-flop": [A(25)], "Flop": [A(40)], "Turn": [Acao(PAGAR)]}),
                   ("Elisa", 1000, "9d 3s", {"Pré-flop": [Acao(DESISTIR)]}),
                   ("Você", 1000, "6c 6d", None)],
        botao=0, mesa="6h 7h 8c 2s Kd"),
    Cenario(
        id="defesa_bb",
        titulo="Defesa do big blind",
        descricao=("Heads-up. Fábio (botão) aumenta para 20 e você está no big blind com K♦9♣."),
        analise=("Contra um aumento mínimo você paga 10 para disputar um pote de 30: pot odds de 25%. "
                 "Quase qualquer mão razoável tem essa equity contra o range amplo de um botão, então "
                 "o big blind deve defender bastante (pagar ou dar 3-bet). K9o é uma defesa clara; "
                 "desistir aqui é um vazamento comum. Fábio tinha Q♠5♠."),
        jogadores=[("Fábio", 1000, "Qs 5s", {"Pré-flop": [A(20)], "Flop": [A(15)]}),
                   ("Você", 1000, "Kd 9c", None)],
        botao=0, mesa="Kh 8d 3s 6c Jd"),
]


def por_id(cid: str) -> Cenario:
    for c in CENARIOS:
        if c.id == cid:
            return c
    raise KeyError(cid)
