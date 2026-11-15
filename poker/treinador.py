"""Modo treinador: comenta cada decisão sua com base nos ranges de posição
(pré-flop) e na comparação entre equity e pot odds (pós-flop).

As recomendações são heurísticas de estudo, não uma solução de teoria dos jogos.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence

from .acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao, EstadoMao, Opcoes
from .bots import estimar_equity
from .cartas import Carta
from .ranges import ABERTURA, NOME_POSICAO, classe_mao, deve_abrir, percentil

OK, ALERTA, INFO = "ok", "alerta", "info"


@dataclass
class Comentario:
    nivel: str
    texto: str
    equity: Optional[float] = None
    pot_odds: Optional[float] = None

    def __str__(self) -> str:
        marca = {"ok": "✔", "alerta": "⚠", "info": "•"}[self.nivel]
        return f"[Treinador] {marca} {self.texto}"


def _tipo(acao: Acao, op: Opcoes) -> str:
    t = acao.tipo
    if t == ALL_IN:
        return AUMENTAR if op.pode_aumentar and op.max_para > op.aposta_atual else PAGAR
    if t == PAGAR and op.para_pagar == 0:
        return PASSAR
    return t


def comentar(cartas: Sequence[Carta], estado: EstadoMao, op: Opcoes, acao: Acao,
             rng: Optional[random.Random] = None, simulacoes: int = 600) -> Comentario:
    rng = rng or random.Random()
    t = _tipo(acao, op)
    if estado.rodada == "Pré-flop":
        return _preflop(cartas, estado, op, t)
    return _posflop(cartas, estado, op, t, rng, simulacoes)


def _preflop(cartas, estado: EstadoMao, op: Opcoes, t: str) -> Comentario:
    classe = classe_mao(*cartas)
    pct = percentil(classe)
    pos = estado.posicao
    nome_pos = NOME_POSICAO.get(pos, pos)
    top = f"{classe} está no top {pct + 0.1:.0f}% das mãos"

    if estado.aumentos == 0:
        if op.pode_passar:  # big blind sem aumento
            if t == DESISTIR:
                return Comentario(ALERTA, "Você podia passar de graça no big blind; nunca desista sem aposta a pagar.")
            if t == AUMENTAR and pct >= 10:
                return Comentario(INFO, f"Aumentar no BB depois de limps pede mão forte; {top}.")
            return Comentario(OK, f"Decisão razoável no big blind ({top}).")
        recomenda = deve_abrir(classe, pos)
        faixa = f"o range de abertura do {nome_pos} é o top {ABERTURA.get(pos, 20):.0f}%"
        if t == AUMENTAR:
            if recomenda:
                return Comentario(OK, f"Boa abertura: {top} e {faixa}.")
            return Comentario(ALERTA, f"Abertura solta: {top}, mas {faixa}. Prefira desistir aqui.")
        if t == PAGAR:
            if recomenda:
                return Comentario(ALERTA, f"Evite só pagar (limp): {top}; entre aumentando (~2,5 BB).")
            return Comentario(ALERTA, f"Limp com mão fora do range ({top}; {faixa}). Desistir é melhor.")
        if t == DESISTIR:
            if recomenda:
                return Comentario(ALERTA, f"Mão lucrativa para abrir: {top} e {faixa}.")
            return Comentario(OK, f"Desistir está certo: {top}, fora do range ({faixa}).")
        return Comentario(INFO, top)

    if estado.aumentos == 1:
        pote_apos = estado.pote + op.para_pagar
        odds = op.para_pagar / pote_apos if pote_apos else 0
        limiar_3bet, limiar_call = 4.0, 14.0 + (12 if odds < 0.3 else 0)
        if t == AUMENTAR:
            if pct < limiar_3bet:
                return Comentario(OK, f"3-bet por valor: {top}.")
            if pct < limiar_call + 10 and pos in ("BTN", "CO", "SB", "BB"):
                return Comentario(INFO, f"3-bet leve ({top}); funciona como blefe ocasional em posição tardia.")
            return Comentario(ALERTA, f"3-bet arriscado com {classe} (top {pct:.0f}%). Contra uma abertura, reserve o 3-bet para mãos fortes.")
        if t == PAGAR:
            if pct < limiar_3bet:
                return Comentario(INFO, f"Mão forte para 3-bet ({top}); só pagar deixa valor na mesa.")
            if pct < limiar_call:
                return Comentario(OK, f"Pagar a abertura é razoável ({top}, pot odds {odds:.0%}).")
            return Comentario(ALERTA, f"Pagamento solto: {top}. Contra aumento, mãos fora do top ~{limiar_call:.0f}% costumam perder dinheiro.")
        if t == DESISTIR:
            if pct < limiar_call * 0.7:
                return Comentario(ALERTA, f"Desistência apertada: {top}; dá para pagar ou dar 3-bet.")
            return Comentario(OK, f"Desistir contra o aumento é aceitável ({top}).")

    # 3-bet ou mais
    if t in (AUMENTAR,) and pct < 3:
        return Comentario(OK, f"Mão premium ({top}); reaumentar está certo.")
    if t == PAGAR and pct < 6:
        return Comentario(OK, f"Pagar o 3-bet com {classe} é razoável.")
    if t == DESISTIR and pct >= 4:
        return Comentario(OK, f"Contra 3-bet/4-bet, desistir com {classe} é o padrão.")
    if t == DESISTIR:
        return Comentario(ALERTA, f"{classe} é forte demais para desistir contra o reaumento ({top}).")
    return Comentario(ALERTA, f"Pote reaumentado: com {classe} (top {pct:.0f}%) continuar é arriscado.")


def _posflop(cartas, estado: EstadoMao, op: Opcoes, t: str, rng, simulacoes) -> Comentario:
    n = max(1, estado.num_oponentes)
    eq = estimar_equity(cartas, estado.comunitarias, n, rng, simulacoes)
    pote_apos = estado.pote + op.para_pagar
    odds = op.para_pagar / pote_apos if op.para_pagar else 0.0
    forte = eq >= min(0.75, 1.25 / (n + 1))
    base = f"equity ≈ {eq:.0%} contra {n} mão(s) aleatória(s)"

    if op.para_pagar == 0:
        if t == AUMENTAR:
            if forte:
                return Comentario(OK, f"Aposta por valor ({base}).", eq, odds)
            return Comentario(INFO, f"Aposta com mão fraca ({base}): é um blefe. Use com moderação e em boas texturas.", eq, odds)
        if t == PASSAR and forte:
            return Comentario(ALERTA, f"Mão forte ({base}); apostar por valor costuma render mais que passar.", eq, odds)
        if t == DESISTIR:
            return Comentario(ALERTA, "Desistiu podendo passar de graça.", eq, odds)
        return Comentario(OK, f"Passar está bem ({base}).", eq, odds)

    precisa = f"precisava de {odds:.0%} (pot odds) e tinha {base}"
    if t == PAGAR:
        if eq >= odds:
            return Comentario(OK, f"Pagamento correto: {precisa}.", eq, odds)
        if eq >= odds * 0.8 and estado.rodada != "River":
            return Comentario(INFO, f"Pagamento no limite: {precisa}; só se justifica pelas odds implícitas.", eq, odds)
        return Comentario(ALERTA, f"Pagamento sem odds: {precisa}.", eq, odds)
    if t == DESISTIR:
        if eq >= odds * 1.25:
            return Comentario(ALERTA, f"Desistência cara: {precisa}. Pagar seria lucrativo contra mãos aleatórias.", eq, odds)
        return Comentario(OK, f"Desistir está certo: {precisa}.", eq, odds)
    if t == AUMENTAR:
        if forte:
            return Comentario(OK, f"Aumento por valor ({base}).", eq, odds)
        return Comentario(INFO, f"Aumento com mão fraca ({base}): blefe/semi-blefe arriscado.", eq, odds)
    return Comentario(INFO, base, eq, odds)
