"""Avaliação de mãos de poker (5 a 7 cartas).

`avaliar` devolve uma tupla comparável: (categoria, desempates). Quanto maior,
melhor. Duas mãos com a mesma tupla empatam (dividem o pote).

Categorias:
    8 Straight flush   7 Quadra   6 Full house   5 Flush   4 Sequência
    3 Trinca           2 Dois pares   1 Um par   0 Carta alta
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional, Sequence, Tuple

from .cartas import Carta

Forca = Tuple[int, Tuple[int, ...]]

CATEGORIAS = [
    "Carta alta", "Um par", "Dois pares", "Trinca", "Sequência",
    "Flush", "Full house", "Quadra", "Straight flush",
]

_NOME = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
         10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}


def _maior_sequencia(valores: Iterable[int]) -> Optional[int]:
    """Carta mais alta da maior sequência de 5, ou None. O Ás vale 1 na 'roda' (A-2-3-4-5)."""
    vs = set(valores)
    if 14 in vs:
        vs.add(1)
    for topo in range(14, 4, -1):
        if all((topo - i) in vs for i in range(5)):
            return topo
    return None


def avaliar(cs: Sequence[Carta]) -> Forca:
    if not 5 <= len(cs) <= 7:
        raise ValueError("A avaliação usa de 5 a 7 cartas.")
    valores = [c.valor for c in cs]

    por_naipe: dict = {}
    for c in cs:
        por_naipe.setdefault(c.naipe, []).append(c.valor)
    valores_flush = None
    for vals in por_naipe.values():
        if len(vals) >= 5:
            valores_flush = sorted(vals, reverse=True)

    if valores_flush:
        topo = _maior_sequencia(valores_flush)
        if topo:
            return (8, (topo,))

    contagem = Counter(valores)
    quadras = [v for v, n in contagem.items() if n == 4]
    if quadras:
        q = max(quadras)
        return (7, (q, max(v for v in valores if v != q)))

    trincas = sorted((v for v, n in contagem.items() if n == 3), reverse=True)
    pares = sorted((v for v, n in contagem.items() if n == 2), reverse=True)

    if trincas and (len(trincas) >= 2 or pares):
        t = trincas[0]
        return (6, (t, max(trincas[1:] + pares)))

    if valores_flush:
        return (5, tuple(valores_flush[:5]))

    topo = _maior_sequencia(valores)
    if topo:
        return (4, (topo,))

    if trincas:
        t = trincas[0]
        kickers = sorted((v for v in valores if v != t), reverse=True)[:2]
        return (3, (t, *kickers))

    if len(pares) >= 2:
        p1, p2 = pares[:2]
        kicker = max(v for v in valores if v not in (p1, p2))
        return (2, (p1, p2, kicker))

    if pares:
        p = pares[0]
        kickers = sorted((v for v in valores if v != p), reverse=True)[:3]
        return (1, (p, *kickers))

    return (0, tuple(sorted(valores, reverse=True)[:5]))


def descrever(forca: Forca) -> str:
    """Texto em português para a mão avaliada."""
    cat, d = forca
    n = [_NOME[v] for v in d]
    if cat == 8:
        return "Royal flush" if d[0] == 14 else f"Straight flush até {n[0]}"
    if cat == 7:
        return f"Quadra de {n[0]} (kicker {n[1]})"
    if cat == 6:
        return f"Full house, {n[0]} com {n[1]}"
    if cat == 5:
        return f"Flush ({' '.join(n)})"
    if cat == 4:
        return f"Sequência até {n[0]}"
    if cat == 3:
        return f"Trinca de {n[0]} (kickers {' '.join(n[1:])})"
    if cat == 2:
        return f"Dois pares, {n[0]} e {n[1]} (kicker {n[2]})"
    if cat == 1:
        return f"Um par de {n[0]} (kickers {' '.join(n[1:])})"
    return f"Carta alta ({' '.join(n)})"
