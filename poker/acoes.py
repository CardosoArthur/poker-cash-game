"""Tipos compartilhados entre a mesa, os bots e as interfaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .cartas import Carta

DESISTIR = "desistir"
PASSAR = "passar"
PAGAR = "pagar"
AUMENTAR = "aumentar"   # também cobre "apostar" quando ninguém apostou na rodada
ALL_IN = "allin"


@dataclass
class Acao:
    tipo: str
    para: int = 0  # em AUMENTAR: valor TOTAL da aposta do jogador na rodada


@dataclass
class Opcoes:
    """O que o jogador da vez pode fazer."""
    pode_passar: bool
    para_pagar: int        # fichas necessárias para pagar (já limitado ao stack)
    pode_aumentar: bool
    min_para: int          # menor aumento válido (total na rodada)
    max_para: int          # all-in (total na rodada)
    aposta_atual: int      # maior aposta da rodada
    ja_apostado: int       # quanto o jogador já pôs nesta rodada


@dataclass
class InfoJogador:
    nome: str
    fichas: int
    aposta_rodada: int
    desistiu: bool
    all_in: bool
    botao: bool
    posicao: str = ""
    contribuicao: int = 0


@dataclass
class EstadoMao:
    """Visão pública da mão (o que qualquer jogador pode saber)."""
    numero_mao: int
    rodada: str
    comunitarias: List[Carta]
    pote: int
    big_blind: int
    num_oponentes: int
    jogadores: List[InfoJogador] = field(default_factory=list)
    posicao: str = ""                 # posição de quem vai agir
    aumentos: int = 0                 # aumentos/apostas já feitos nesta rodada
    agressor: Optional[str] = None    # último a apostar/aumentar nesta rodada
    agressor_preflop: Optional[str] = None
    # Perfil observado de cada jogador (VPIP, PFR, etc.), usado pelos bots.
    perfis: Dict[str, dict] = field(default_factory=dict)
    # Quem pagou/aumentou no pré-flop (para estimar ranges).
    entrou_preflop: Dict[str, str] = field(default_factory=dict)
