"""Força das mãos iniciais, posições na mesa e ranges de abertura.

A ordem das 169 mãos foi calculada por simulação (equity contra 1 e 3 mãos
aleatórias) e ajustada à mão para os pares baixos, que valem mais pelo
potencial de trinca do que a equity crua indica.
"""
from __future__ import annotations

import random
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .cartas import Carta, baralho_completo

ORDEM = """AA KK QQ JJ TT 99 AKs AQs 88 AJs KQs AKo ATs AQo KJs QJs KTs AJo KQo ATo 77 QTs A9s A7s A8s KJo 66 A6s A5s 55 K9s 44 KTo A4s JTs Q9s QJo K8s A9o QTo A7o JTo A3s K7s A8o T9s K9o A5o A2s 33 Q9o K6s Q8s 22 J9s A6o T8s J9o K3s J8s K5s A4o K2s K4s K7o K8o Q7s Q8o 98s Q5s A2o Q6s K6o T9o A3o J7s T7s Q4s J8o 97s K4o J5s T8o J6s K5o Q3s 87s 98o Q7o Q2s T6s 76s J4s Q6o J7o T5s 95s 96s Q5o 86s K3o J3s J2s K2o 75s T6o 65s 87o 96o J5o T4s J6o T7o 85s T3s Q4o 97o T2s J4o Q3o 93s 86o 64s Q2o 84s 54s 74s T4o 73s J2o 76o 94s 92s 95o J3o 85o T5o 75o 43s 63s 65o 53s T3o 82s 83s 52s 93o 42s 64o 94o 54o 74o 72s 62s T2o 84o 53o 32s 73o 92o 63o 43o 82o 52o 83o 42o 62o 32o 72o""".split()

_LETRAS = "AKQJT98765432"
_VALOR = {c: 14 - i for i, c in enumerate(_LETRAS)}
_LETRA = {v: c for c, v in _VALOR.items()}


def combos(classe: str) -> int:
    if len(classe) == 2:
        return 6
    return 4 if classe[2] == "s" else 12


# Percentual acumulado ANTES de cada classe (0 = melhor mão).
_INICIO: Dict[str, float] = {}
_acum = 0
for _c in ORDEM:
    _INICIO[_c] = _acum / 1326 * 100
    _acum += combos(_c)
_RANK = {c: i for i, c in enumerate(ORDEM)}


def classe_mao(c1: Carta, c2: Carta) -> str:
    """Duas cartas -> 'AKs', 'T9o', 'QQ'."""
    a, b = sorted((c1.valor, c2.valor), reverse=True)
    if a == b:
        return _LETRA[a] * 2
    return _LETRA[a] + _LETRA[b] + ("s" if c1.naipe == c2.naipe else "o")


def percentil(classe: str) -> float:
    """Quantos % das mãos são melhores que esta (0 = AA)."""
    return _INICIO[classe]


def no_range(classe: str, pct: float) -> bool:
    """A mão está entre as melhores pct% das mãos?"""
    return _INICIO[classe] < pct


def range_top(pct: float) -> Set[str]:
    return {c for c in ORDEM if no_range(c, pct)}


# ------------------------------------------------------------------ posições
_DEPOIS_DO_BB = {
    0: [], 1: ["CO"], 2: ["HJ", "CO"], 3: ["UTG", "HJ", "CO"],
    4: ["UTG", "MP", "HJ", "CO"], 5: ["UTG", "UTG+1", "MP", "HJ", "CO"],
    6: ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO"],
}


def nomes_posicoes(n: int) -> List[str]:
    """Nomes das posições a partir do botão, para n jogadores na mão."""
    if n < 2:
        return ["BTN"][:n]
    if n == 2:
        return ["BTN", "BB"]  # heads-up: o botão é o small blind
    return ["BTN", "SB", "BB"] + _DEPOIS_DO_BB[n - 3]


POSICOES = ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"]

# % de mãos para abrir com aumento quando ninguém entrou no pote (RFI).
ABERTURA: Dict[str, float] = {
    "UTG": 12, "UTG+1": 14, "MP": 16, "LJ": 18, "HJ": 21,
    "CO": 28, "BTN": 45, "SB": 36, "BB": 40,
}

NOME_POSICAO = {
    "UTG": "primeira posição (UTG)", "UTG+1": "UTG+1", "MP": "posição do meio (MP)",
    "LJ": "lojack (LJ)", "HJ": "hijack (HJ)", "CO": "cutoff (CO)",
    "BTN": "botão (BTN)", "SB": "small blind (SB)", "BB": "big blind (BB)",
}


def deve_abrir(classe: str, posicao: str) -> bool:
    return no_range(classe, ABERTURA.get(posicao, 20))


def grade(selecionadas: Iterable[str], marca: str = "■", vazio: str = "·") -> str:
    """Tabela 13x13: pares na diagonal, suited acima, offsuit abaixo."""
    sel = set(selecionadas)
    linhas = ["     " + "".join(f"{c:>4}" for c in _LETRAS)]
    for i, a in enumerate(_LETRAS):
        cel = []
        for j, b in enumerate(_LETRAS):
            if i == j:
                c = a + b
            elif i < j:
                c = a + b + "s"
            else:
                c = b + a + "o"
            cel.append(f"{marca if c in sel else vazio:>4}")
        linhas.append(f"  {a}  " + "".join(cel))
    return "\n".join(linhas)


def tabela_posicao(posicao: str) -> str:
    pct = ABERTURA[posicao]
    sel = range_top(pct)
    lista = [c for c in ORDEM if c in sel]
    return (f"Abertura no {NOME_POSICAO[posicao]} — top {pct:.0f}% das mãos "
            f"({sum(combos(c) for c in sel)} combinações)\n"
            "(linhas = 1ª carta; acima da diagonal = suited, abaixo = offsuit)\n"
            + grade(sel) + "\n" + "Mãos: " + " ".join(lista))


def amostrar_do_range(pct: float, excluir: Iterable[Carta], rng: random.Random,
                      baralho: Optional[Sequence[Carta]] = None, tentativas: int = 200) -> List[Carta]:
    """Sorteia duas cartas dentro do top pct% (amostragem por rejeição)."""
    ex = set(excluir)
    cartas = [c for c in (baralho or baralho_completo()) if c not in ex]
    pct = max(pct, 1.0)
    for _ in range(tentativas):
        a, b = rng.sample(cartas, 2)
        if pct >= 100 or no_range(classe_mao(a, b), pct):
            return [a, b]
    return rng.sample(cartas, 2)
