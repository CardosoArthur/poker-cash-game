"""Montagem do pote principal, side pots e divisão entre vencedores.

A ideia: cada jogador colocou `contribuicao[j]` fichas na mão. Os níveis
distintos de contribuição definem "fatias". Uma fatia entre os níveis L1 e L2
recebe (L2 - L1) de cada jogador que contribuiu ao menos L2, e só pode ser
ganha por quem não desistiu e contribuiu ao menos L2. Quem desistiu deixa as
fichas no pote mas não concorre.

Uma fatia com um único contribuinte é aposta não paga: volta para o dono.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Hashable, Iterable, List, Sequence, Set, Tuple


@dataclass
class Pote:
    valor: int
    elegiveis: List[Hashable]
    contribuintes: int = 0  # quantos jogadores puseram fichas nesta fatia

    @property
    def devolucao(self) -> bool:
        """Aposta que ninguém pagou: só o próprio dono contribuiu."""
        return self.contribuintes == 1


@dataclass
class Divisao:
    pote: Pote
    vencedores: List[Hashable]
    premios: Dict[Hashable, int] = field(default_factory=dict)


def calcular_potes(contribuicoes: Dict[Hashable, int],
                   desistiram: Iterable[Hashable] = ()) -> List[Pote]:
    """Separa as contribuições em pote principal + side pots.

    A ordem das chaves em `contribuicoes` é preservada na lista de elegíveis.
    """
    desist: Set[Hashable] = set(desistiram)
    niveis = sorted({v for v in contribuicoes.values() if v > 0})
    potes: List[Pote] = []
    anterior = 0
    for nivel in niveis:
        participantes = [j for j, v in contribuicoes.items() if v >= nivel]
        valor = (nivel - anterior) * len(participantes)
        elegiveis = [j for j in participantes if j not in desist]
        anterior = nivel
        if not elegiveis:
            # Só desistentes nesta fatia (situação rara): vai para o pote anterior.
            if potes:
                potes[-1].valor += valor
                continue
            raise ValueError("Pote sem nenhum jogador elegível.")
        if (potes and potes[-1].elegiveis == elegiveis
                and potes[-1].devolucao == (len(participantes) == 1)):
            # Mesma disputa: junta com a fatia anterior.
            potes[-1].valor += valor
            potes[-1].contribuintes = max(potes[-1].contribuintes, len(participantes))
        else:
            potes.append(Pote(valor, elegiveis, len(participantes)))
    return potes


def distribuir_potes(potes: Sequence[Pote],
                     forcas: Dict[Hashable, Tuple],
                     ordem_desempate: Sequence[Hashable]) -> Tuple[Dict[Hashable, int], List[Divisao]]:
    """Distribui cada pote entre a(s) melhor(es) mão(s) elegíveis.

    Em empate, o pote é dividido igualmente; as fichas que sobram da divisão
    (fichas ímpares) vão, uma a uma, para os vencedores na ordem
    `ordem_desempate` (convenção: primeiro à esquerda do botão).
    """
    ganhos: Dict[Hashable, int] = {}
    divisoes: List[Divisao] = []
    posicao = {j: i for i, j in enumerate(ordem_desempate)}
    for pote in potes:
        if len(pote.elegiveis) == 1:
            vencedores = list(pote.elegiveis)
        else:
            melhor = max(forcas[j] for j in pote.elegiveis)
            vencedores = [j for j in pote.elegiveis if forcas[j] == melhor]
        vencedores.sort(key=lambda j: posicao.get(j, len(posicao)))
        parte, resto = divmod(pote.valor, len(vencedores))
        premios = {j: parte for j in vencedores}
        for j in vencedores[:resto]:
            premios[j] += 1
        for j, v in premios.items():
            ganhos[j] = ganhos.get(j, 0) + v
        divisoes.append(Divisao(pote, vencedores, premios))
    return ganhos, divisoes
