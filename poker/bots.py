"""Estratégia dos bots, em três níveis de dificuldade.

- fácil: compara a equity contra mãos aleatórias com as pot odds, com erros de
  propósito (paga demais, blefa sem critério).
- médio: pré-flop por ranges de posição (abrir, 3-bet, pagar); pós-flop por
  equity contra mãos aleatórias, pot odds e apostas de 1/2 a 3/4 do pote.
- difícil: como o médio, mas estima o range de cada oponente pelo que ele fez
  no pré-flop e pelo perfil observado (VPIP/PFR), adapta-se a jogadores soltos,
  apertados ou agressivos (incluindo você), faz continuation bets e semi-blefes.

O estilo (conservador, equilibrado, agressivo, solto) ajusta a abertura dos
ranges e a frequência de agressão em qualquer nível.
"""
from __future__ import annotations

import random
from typing import List, Optional, Sequence

from .acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao, EstadoMao, Opcoes
from .avaliador import avaliar
from .cartas import Carta, baralho_completo
from .ranges import ABERTURA, amostrar_do_range, classe_mao, percentil


def estimar_equity(minhas: Sequence[Carta], mesa: Sequence[Carta], num_oponentes: int,
                   rng: random.Random, simulacoes: int = 150,
                   ranges: Optional[Sequence[float]] = None) -> float:
    """Fração esperada do pote (vitórias + empates divididos) por Monte Carlo.

    ``ranges``: para cada oponente, o top X% de mãos que ele pode ter
    (100 = qualquer mão). Sem ``ranges``, todos jogam mãos aleatórias.
    """
    n = max(1, min(num_oponentes, 6))
    rs = list(ranges or [])[:n]
    rs += [100.0] * (n - len(rs))
    usa_range = any(r < 100 for r in rs)
    conhecidas = set(minhas) | set(mesa)
    resto = [c for c in baralho_completo() if c not in conhecidas]
    faltam = 5 - len(mesa)
    total = 0.0
    for _ in range(simulacoes):
        if usa_range:
            usadas: set = set()
            maos = []
            for r in rs:
                m = amostrar_do_range(r, usadas, rng, resto, tentativas=60)
                usadas.update(m)
                maos.append(m)
            mesa_final = list(mesa) + rng.sample([c for c in resto if c not in usadas], faltam)
        else:
            amostra = rng.sample(resto, faltam + 2 * n)
            mesa_final = list(mesa) + amostra[:faltam]
            maos = [amostra[faltam + 2 * k: faltam + 2 * k + 2] for k in range(n)]
        minha = avaliar(list(minhas) + mesa_final)
        empates = 0
        perdeu = False
        for m in maos:
            f = avaliar(list(m) + mesa_final)
            if f > minha:
                perdeu = True
                break
            if f == minha:
                empates += 1
        if not perdeu:
            total += 1.0 / (1 + empates)
    return total / simulacoes


NOMES_BOTS: List[str] = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabi",
                         "Hugo", "Íris", "Joana", "Kauã", "Lia", "Marcos", "Nina"]

# estilo: (agressividade, soltura)
ESTILOS = {
    "conservador": (0.25, 0.10),
    "equilibrado": (0.50, 0.30),
    "agressivo": (0.80, 0.45),
    "solto": (0.40, 0.70),
}

MIN_MAOS_PERFIL = 15  # mãos observadas antes de confiar no perfil de um oponente


class EstrategiaBot:
    def __init__(self, rng: random.Random, estilo: str = "equilibrado", dificuldade: str = "medio"):
        self.rng = rng
        self.estilo = estilo
        self.dificuldade = dificuldade
        self.agressividade, self.soltura = ESTILOS[estilo]

    # ------------------------------------------------------------ entrada
    def decidir(self, minhas: Sequence[Carta], estado: EstadoMao, op: Opcoes) -> Acao:
        if self.dificuldade == "facil":
            return self._facil(minhas, estado, op)
        if estado.rodada == "Pré-flop":
            return self._preflop(minhas, estado, op)
        return self._posflop(minhas, estado, op)

    # ------------------------------------------------------------ utilidades
    def _para(self, op: Opcoes, para: int) -> Acao:
        para = max(op.min_para, int(para))
        if para >= op.max_para * 0.85:
            return Acao(ALL_IN)
        return Acao(AUMENTAR, para)

    def _desiste_ou_passa(self, op: Opcoes) -> Acao:
        return Acao(PASSAR if op.pode_passar else DESISTIR)

    def _perfil(self, estado: EstadoMao, nome: Optional[str]) -> Optional[dict]:
        if not nome:
            return None
        p = estado.perfis.get(nome)
        if p and p["maos"] >= MIN_MAOS_PERFIL:
            return p
        return None

    def _range_oponente(self, estado: EstadoMao, info) -> float:
        """Estimativa do top X% de mãos de um oponente ainda na mão."""
        entrou = estado.entrou_preflop.get(info.nome)
        perfil = self._perfil(estado, info.nome)
        if entrou == "aumentou":
            pct = perfil["pfr"] if perfil and perfil["pfr"] else ABERTURA.get(info.posicao, 20)
        elif entrou == "pagou":
            pct = perfil["vpip"] if perfil and perfil["vpip"] else 35
        else:
            pct = 100  # big blind que só passou, ou blinds
        return max(5.0, min(100.0, pct))

    # ------------------------------------------------------------ fácil
    def _facil(self, minhas, estado: EstadoMao, op: Opcoes) -> Acao:
        rng = self.rng
        n_op = max(1, estado.num_oponentes)
        eq = estimar_equity(minhas, estado.comunitarias, n_op, rng, 100)
        eq_rel = eq * (n_op + 1)
        pote_apos = estado.pote + op.para_pagar
        pot_odds = op.para_pagar / pote_apos if op.para_pagar else 0.0
        if op.pode_aumentar and eq_rel >= 1.7 - 0.5 * self.agressividade and rng.random() > 0.15:
            return self._para(op, op.aposta_atual + max(estado.big_blind, pote_apos * rng.choice([0.5, 1.0])))
        if op.para_pagar == 0:
            if op.pode_aumentar and rng.random() < 0.15 * self.agressividade:
                return self._para(op, op.aposta_atual + max(estado.big_blind, pote_apos * 0.5))
            return Acao(PASSAR)
        if eq >= pot_odds * (1.0 - 0.35 * self.soltura) or rng.random() < 0.12:
            return Acao(PAGAR)  # o 12% é um erro proposital: pagar sem odds
        return Acao(DESISTIR)

    # ------------------------------------------------------------ pré-flop
    def _preflop(self, minhas, estado: EstadoMao, op: Opcoes) -> Acao:
        rng = self.rng
        pct = percentil(classe_mao(*minhas))
        ajuste = (self.soltura - 0.3) * 15
        aposta = op.aposta_atual
        bb = estado.big_blind
        dificil = self.dificuldade == "dificil"
        pote_apos = estado.pote + op.para_pagar
        pot_odds = op.para_pagar / pote_apos if op.para_pagar else 0.0
        limpers = sum(1 for v in estado.entrou_preflop.values() if v == "pagou")

        if estado.aumentos == 0:
            if op.pode_passar:  # big blind sem aumento
                if op.pode_aumentar and pct < 8 + ajuste:
                    return self._para(op, aposta * (3 + limpers))
                return Acao(PASSAR)
            abrir = ABERTURA.get(estado.posicao, 20) + ajuste
            if limpers:
                abrir *= 0.7  # isolar limpers pede mão melhor
            if op.pode_aumentar and pct < abrir:
                fator = 3.0 if estado.posicao == "SB" else 2.5
                return self._para(op, aposta * fator + limpers * aposta)
            if estado.posicao == "SB" and pct < 50 and rng.random() < 0.2 + 0.5 * self.soltura:
                return Acao(PAGAR)  # completa o small blind
            if limpers and pct < 30 + ajuste and pot_odds < 0.2:
                return Acao(PAGAR)  # limp atrás com mão especulativa
            return self._desiste_ou_passa(op)

        agressor = self._perfil(estado, estado.agressor)
        if estado.aumentos == 1:
            if dificil and agressor:
                range_agr = max(5.0, agressor["pfr"] or 15)
            else:
                info = next((i for i in estado.jogadores if i.nome == estado.agressor), None)
                range_agr = ABERTURA.get(info.posicao, 18) if info else 18
            limiar_3bet = max(2.5, range_agr * 0.25) + self.agressividade * 2
            limiar_call = range_agr * 0.8 + self.soltura * 6
            if pot_odds < 0.3:          # preço bom (ex.: BB contra min-raise)
                limiar_call += 12
            if op.pode_aumentar and pct < limiar_3bet:
                return self._para(op, aposta * 3 + (estado.pote - aposta - op.ja_apostado) * 0.5)
            if pct < limiar_call:
                return Acao(PAGAR)
            if dificil and op.pode_aumentar and estado.posicao in ("BTN", "CO", "SB", "BB") \
                    and pct < limiar_call + 15 and rng.random() < 0.08 * self.agressividade:
                return self._para(op, aposta * 3)  # 3-bet blefe ocasional
            return self._desiste_ou_passa(op)

        # 4-bet ou mais
        if op.pode_aumentar and pct < 2.5:
            return self._para(op, aposta * 2.3)
        if pct < 5 + self.soltura * 4 and op.para_pagar <= (op.max_para - op.ja_apostado) * 0.4:
            return Acao(PAGAR)
        return self._desiste_ou_passa(op)

    # ------------------------------------------------------------ pós-flop
    def _posflop(self, minhas, estado: EstadoMao, op: Opcoes) -> Acao:
        rng = self.rng
        dificil = self.dificuldade == "dificil"
        oponentes = [i for i in estado.jogadores if not i.desistiu and i.posicao != estado.posicao]
        n_op = max(1, len(oponentes))
        ranges = [self._range_oponente(estado, i) for i in oponentes] if dificil else None
        eq = estimar_equity(minhas, estado.comunitarias, n_op, rng,
                            180 if dificil else 150, ranges)
        if not dificil and estado.aumentos:
            # contra apostas/aumentos, a equity contra mãos aleatórias superestima a mão
            eq = max(0.0, eq - 0.08 * estado.aumentos)
        pote_apos = estado.pote + op.para_pagar
        pot_odds = op.para_pagar / pote_apos if op.para_pagar else 0.0
        forte = eq >= min(0.75, 1.25 / (n_op + 1))
        # cada aumento já feito na rodada exige uma mão mais perto dos nuts para reaumentar
        muito_forte = eq >= min(0.95, 1.6 / (n_op + 1) + 0.07 * estado.aumentos)
        river = estado.rodada == "River"
        sou_agressor = estado.agressor_preflop is not None and \
            estado.agressor_preflop not in [o.nome for o in oponentes]

        if op.para_pagar == 0:
            if not op.pode_aumentar:
                return Acao(PASSAR)
            if muito_forte and not river and rng.random() < 0.12:
                return Acao(PASSAR)  # slowplay ocasional
            if forte:
                frac = 0.75 if (muito_forte and river) else 0.66
                return self._para(op, max(estado.big_blind, estado.pote * frac))
            cbet = 0.45 + 0.25 * self.agressividade
            if dificil and sou_agressor and n_op == 1 and estado.rodada == "Flop" and rng.random() < cbet:
                return self._para(op, max(estado.big_blind, estado.pote * 0.4))  # continuation bet
            if dificil and not river and eq >= 0.3 / n_op * 1.0 and rng.random() < 0.3 * self.agressividade:
                return self._para(op, max(estado.big_blind, estado.pote * 0.5))  # semi-blefe
            if rng.random() < 0.06 * self.agressividade:
                return self._para(op, max(estado.big_blind, estado.pote * 0.5))
            return Acao(PASSAR)

        if muito_forte and op.pode_aumentar:
            return self._para(op, op.aposta_atual * 3 + estado.pote * 0.3)

        margem = 1.0 - 0.2 * self.soltura
        if dificil:
            agr = self._perfil(estado, estado.agressor)
            if agr and agr["af"] is not None:
                if agr["af"] >= 3:
                    margem *= 0.85   # apostador frequente: pague mais leve
                elif agr["af"] < 1:
                    margem *= 1.2    # jogador passivo apostando: respeite
            if not river:
                margem *= 0.92       # odds implícitas com draws
        if eq >= pot_odds * margem:
            return Acao(PAGAR)
        if dificil and op.pode_aumentar and not river and rng.random() < 0.04 * self.agressividade:
            return self._para(op, op.aposta_atual * 2.5)
        return Acao(DESISTIR)
