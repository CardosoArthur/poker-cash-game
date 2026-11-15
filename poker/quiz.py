"""Quiz pré-flop: você recebe uma mão e uma posição, com ninguém tendo entrado
no pote antes de você, e decide se abre com aumento ou desiste. A resposta é
comparada com o range de abertura da posição (veja ``ranges.ABERTURA``)."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from .cartas import Carta, baralho_completo
from .ranges import ABERTURA, NOME_POSICAO, classe_mao, deve_abrir, percentil

POSICOES_QUIZ = ["UTG", "MP", "HJ", "CO", "BTN", "SB"]


@dataclass
class Pergunta:
    cartas: List[Carta]
    posicao: str
    classe: str
    abrir: bool  # resposta correta

    def enunciado(self) -> str:
        from .cartas import formatar
        return (f"Você está no {NOME_POSICAO[self.posicao]} com {formatar(self.cartas)} ({self.classe}). "
                "Todos antes de você desistiram. Aumentar (a) ou desistir (d)?")

    def explicacao(self) -> str:
        pct = percentil(self.classe)
        lim = ABERTURA[self.posicao]
        decisao = "aumentar" if self.abrir else "desistir"
        return (f"{self.classe} está no top {pct + 0.1:.0f}% das mãos; o range de abertura do "
                f"{self.posicao} é o top {lim:.0f}%. Resposta: {decisao}.")


def gerar_pergunta(rng: random.Random, posicao: Optional[str] = None) -> Pergunta:
    """70% das perguntas usam mãos perto do limite do range (as que mais ensinam)."""
    posicao = posicao or rng.choice(POSICOES_QUIZ)
    limite = ABERTURA[posicao]
    baralho = baralho_completo()
    for _ in range(500):
        a, b = rng.sample(baralho, 2)
        classe = classe_mao(a, b)
        if rng.random() < 0.3 or abs(percentil(classe) - limite) <= 12:
            return Pergunta([a, b], posicao, classe, deve_abrir(classe, posicao))
    return Pergunta([a, b], posicao, classe, deve_abrir(classe, posicao))


def corrigir(pergunta: Pergunta, resposta: str) -> bool:
    return (resposta.strip().lower().startswith("a")) == pergunta.abrir
