"""Cartas e baralho."""
from __future__ import annotations

import random
from typing import Iterable, List, NamedTuple, Optional

NAIPES = "shdc"  # espadas (spades), copas (hearts), ouros (diamonds), paus (clubs)
VALORES = range(2, 15)  # 11=J, 12=Q, 13=K, 14=A

_SIMBOLOS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
_LETRAS = {"s": "e", "h": "c", "d": "o", "c": "p"}  # espadas, copas, ouros, paus
_NOME_VALOR = {10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}
_LER_VALOR = {"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}

_usar_simbolos = True


def configurar_simbolos(usar: bool) -> None:
    """Desliga os símbolos ♠♥♦♣ em terminais que não os exibem."""
    global _usar_simbolos
    _usar_simbolos = usar


class Carta(NamedTuple):
    valor: int
    naipe: str

    def __str__(self) -> str:
        v = _NOME_VALOR.get(self.valor, str(self.valor))
        n = _SIMBOLOS[self.naipe] if _usar_simbolos else _LETRAS[self.naipe]
        return f"{v}{n}"


def carta(texto: str) -> Carta:
    """Cria uma carta a partir de texto curto, ex.: 'Ah', 'Td', '10c', '9s'."""
    texto = texto.strip()
    v, n = texto[:-1].upper(), texto[-1].lower()
    valor = _LER_VALOR[v] if v in _LER_VALOR else int(v)
    if valor not in VALORES or n not in NAIPES:
        raise ValueError(f"Carta inválida: {texto}")
    return Carta(valor, n)


def cartas(texto: str) -> List[Carta]:
    """'Ah Kd 2c' -> [Carta, Carta, Carta]."""
    return [carta(t) for t in texto.split()]


def formatar(cs: Iterable[Carta]) -> str:
    return " ".join(str(c) for c in cs)


def baralho_completo() -> List[Carta]:
    return [Carta(v, n) for n in NAIPES for v in VALORES]


class Baralho:
    """Baralho de 52 cartas. `ordem_fixa` permite montar cenários nos testes."""

    def __init__(self, rng: Optional[random.Random] = None,
                 ordem_fixa: Optional[List[Carta]] = None):
        if ordem_fixa is not None:
            self._cartas = list(ordem_fixa)
        else:
            self._cartas = baralho_completo()
            (rng or random.Random()).shuffle(self._cartas)

    def distribuir(self, n: int = 1) -> List[Carta]:
        if n > len(self._cartas):
            raise RuntimeError("Baralho sem cartas suficientes.")
        saida, self._cartas = self._cartas[:n], self._cartas[n:]
        return saida

    def __len__(self) -> int:
        return len(self._cartas)
