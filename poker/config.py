"""Configuração da mesa. Tudo pode ser alterado nas perguntas feitas antes de
cada partida, pela linha de comando (`python main.py --help`) ou na interface web."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

MAX_ASSENTOS = 9          # 1 usuário + até 8 bots
MIN_BOTS = 1
MAX_BOTS = MAX_ASSENTOS - 1
DIFICULDADES = ("facil", "medio", "dificil")
NOME_DIFICULDADE = {"facil": "fácil", "medio": "médio", "dificil": "difícil"}


@dataclass
class Configuracao:
    fichas_iniciais: int = 1000   # stack inicial padrão (100 big blinds)
    num_bots: int = 5             # mesa 6-max por padrão
    small_blind: int = 5
    big_blind: int = 10
    # Em cash game, quando um bot quebra ele sai e outro senta com o stack inicial.
    repor_bots: bool = True
    ante: int = 0                 # pago por todos antes da mão (dinheiro morto)
    straddle: bool = False        # jogador à esquerda do BB posta 2x o big blind
    dificuldade: str = "medio"    # facil | medio | dificil
    treinador: bool = True        # comenta as suas decisões

    @property
    def valor_straddle(self) -> int:
        return self.big_blind * 2

    def validar(self) -> None:
        if self.small_blind <= 0 or self.big_blind <= 0:
            raise ValueError("Os blinds precisam ser positivos.")
        if self.small_blind > self.big_blind:
            raise ValueError("O small blind não pode ser maior que o big blind.")
        if self.ante < 0 or self.ante > self.big_blind:
            raise ValueError("O ante deve ficar entre 0 e o big blind.")
        if not (MIN_BOTS <= self.num_bots <= MAX_BOTS):
            raise ValueError(f"O número de bots deve ficar entre {MIN_BOTS} e {MAX_BOTS}.")
        if self.fichas_iniciais < self.big_blind * 2:
            raise ValueError(
                f"As fichas iniciais precisam ser pelo menos 2 big blinds ({self.big_blind * 2})."
            )
        if self.dificuldade not in DIFICULDADES:
            raise ValueError(f"Dificuldade deve ser uma de: {', '.join(DIFICULDADES)}.")

    def para_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Configuracao":
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in nomes})

    def resumo(self) -> str:
        partes = [f"blinds {self.small_blind}/{self.big_blind}"]
        if self.ante:
            partes.append(f"ante {self.ante}")
        if self.straddle:
            partes.append(f"straddle {self.valor_straddle}")
        partes.append(f"stack {self.fichas_iniciais}")
        partes.append(f"{self.num_bots} bot(s) {NOME_DIFICULDADE[self.dificuldade]}")
        return ", ".join(partes)
