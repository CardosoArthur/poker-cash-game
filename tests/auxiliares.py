"""Utilidades compartilhadas pelos testes."""
import random
import shutil
import tempfile

from poker.acoes import ALL_IN, PAGAR, PASSAR, Acao
from poker.cartas import Baralho, baralho_completo, cartas
from poker.config import Configuracao
from poker.mesa import Jogador, Mesa


class Roteiro:
    """Estratégia que executa uma lista fixa de ações (e depois passa/paga)."""

    estilo = "roteiro"

    def __init__(self, acoes):
        self.acoes = list(acoes)

    def decidir(self, minhas, estado, op):
        if self.acoes:
            return self.acoes.pop(0)
        return Acao(PASSAR if op.pode_passar else PAGAR)


class SempreAllIn:
    estilo = "maníaco"

    def decidir(self, minhas, estado, op):
        return Acao(ALL_IN)


def sempre_paga(j, estado, op):
    """Decisor humano de teste: passa quando pode, senão paga."""
    return Acao(PASSAR if op.pode_passar else PAGAR)


def baralho_com(prefixo_txt):
    """Baralho cujas primeiras cartas são as indicadas; o resto segue em ordem."""
    inicio = cartas(prefixo_txt)
    resto = [c for c in baralho_completo() if c not in inicio]
    return Baralho(ordem_fixa=inicio + resto)


def mesa_com(stacks, estrategias, sb=5, bb=10, ante=0, straddle=False, ouvintes=None, humano=None):
    """Mesa com stacks e estratégias definidos. ``humano``: índice do jogador humano."""
    cfg = Configuracao(fichas_iniciais=max(stacks), num_bots=max(1, len(stacks) - 1),
                       small_blind=sb, big_blind=bb, repor_bots=False, ante=ante, straddle=straddle)
    jogadores = [Jogador(n, s, estrategia=e, humano=(i == humano))
                 for i, (n, s, e) in enumerate(zip("ABCDEFGHI", stacks, estrategias))]
    return Mesa(cfg, random.Random(1), jogadores=jogadores, ouvintes=ouvintes,
                decisor_humano=sempre_paga if humano is not None else None)


class PastaTemporaria:
    def __enter__(self):
        self.caminho = tempfile.mkdtemp(prefix="poker_teste_")
        return self.caminho

    def __exit__(self, *a):
        shutil.rmtree(self.caminho, ignore_errors=True)
