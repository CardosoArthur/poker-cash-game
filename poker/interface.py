"""Interface de terminal (em português) para o jogador humano."""
from __future__ import annotations

import random
from typing import Optional

from .acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao, EstadoMao, Opcoes
from .bots import estimar_equity
from .cartas import formatar
from .treinador import comentar

AJUDA = """Comandos:
  d        desistir (fold)
  p        passar (check), quando não há aposta a pagar
  c        pagar (call) — ou passar, se não houver nada a pagar
  a VALOR  apostar / aumentar PARA o valor total indicado na rodada (ex.: a 60)
  t        all-in
  e        estimar sua equity (chance de ganhar) contra mãos aleatórias
  ?        mostrar esta ajuda"""


class EntradaEncerrada(Exception):
    """A entrada padrão acabou (Ctrl+Z/Ctrl+D ou fim de um arquivo redirecionado)."""


def ler(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        print()
        raise EntradaEncerrada()


class InterfaceTerminal:
    def __init__(self, rng: Optional[random.Random] = None, treinador: bool = True):
        self.rng = rng or random.Random()
        self.treinador = treinador
        self.saindo = False  # vira True se a entrada acabar no meio de uma mão
        self.comentarios = []  # comentários do treinador desta sessão

    def mostrar(self, msg: str) -> None:
        print(msg)

    def _mostrar_mesa(self, j, estado: EstadoMao, op: Opcoes) -> None:
        mesa = formatar(estado.comunitarias) if estado.comunitarias else "—"
        print(f"\n[{estado.rodada}] Mesa: {mesa}   Pote: {estado.pote}")
        for info in estado.jogadores:
            marcas = []
            if info.botao:
                marcas.append("D")
            if info.desistiu:
                marcas.append("fora")
            elif info.all_in:
                marcas.append("all-in")
            if info.posicao:
                marcas.insert(0, info.posicao)
            m = f" ({', '.join(marcas)})" if marcas else ""
            seta = "→" if info.nome == j.nome else " "
            print(f" {seta} {info.nome + m:<22} fichas {info.fichas:>6}   aposta {info.aposta_rodada:>5}")
        print(f"Suas cartas: {formatar(j.cartas)} | Suas fichas: {j.fichas} | Para pagar: {op.para_pagar}")
        partes = ["[d] desistir"]
        if op.pode_passar:
            partes.append("[p] passar")
        else:
            partes.append(f"[c] pagar {op.para_pagar}" + (" (all-in)" if op.para_pagar == j.fichas else ""))
        if op.pode_aumentar:
            verbo = "apostar" if op.aposta_atual == 0 else "aumentar para"
            partes.append(f"[a N] {verbo} N (mín {op.min_para}, máx {op.max_para})")
            partes.append("[t] all-in")
        partes.append("[e] equity  [?] ajuda")
        print("Opções: " + "  ".join(partes))

    def decidir(self, j, estado: EstadoMao, op: Opcoes) -> Acao:
        acao = self._ler_acao(j, estado, op)
        if self.treinador and not self.saindo:
            c = comentar(j.cartas, estado, op, acao, self.rng)
            self.comentarios.append(c)
            print(c)
        return acao

    def _ler_acao(self, j, estado: EstadoMao, op: Opcoes) -> Acao:
        self._mostrar_mesa(j, estado, op)
        while True:
            try:
                txt = ler("> ").strip().lower()
            except EntradaEncerrada:
                self.saindo = True
                print("(entrada encerrada — você sai da mesa após esta mão)")
                return Acao(PASSAR if op.pode_passar else DESISTIR)
            if not txt:
                continue
            cmd, *resto = txt.split()
            if cmd in ("?", "h", "ajuda"):
                print(AJUDA)
            elif cmd == "e":
                eq = estimar_equity(j.cartas, estado.comunitarias, estado.num_oponentes,
                                    self.rng, simulacoes=1500)
                odds = op.para_pagar / (estado.pote + op.para_pagar) if op.para_pagar else 0
                print(f"Equity estimada contra {estado.num_oponentes} mão(s) aleatória(s): {eq:.0%}"
                      + (f" | pot odds para pagar: {odds:.0%}" if op.para_pagar else ""))
            elif cmd == "d":
                if op.pode_passar:
                    print("(você poderia passar de graça, mas desistiu)")
                return Acao(DESISTIR)
            elif cmd == "p":
                if op.pode_passar:
                    return Acao(PASSAR)
                print(f"Não dá para passar: há {op.para_pagar} para pagar. Use 'c' ou 'd'.")
            elif cmd == "c":
                return Acao(PASSAR if op.pode_passar else PAGAR)
            elif cmd == "t":
                return Acao(ALL_IN)
            elif cmd == "a":
                if not op.pode_aumentar:
                    print("Aumentar não é permitido agora.")
                    continue
                try:
                    valor = int(resto[0])
                except (IndexError, ValueError):
                    print("Informe o valor total, ex.: a 60")
                    continue
                if valor >= op.max_para:
                    return Acao(ALL_IN)
                if valor < op.min_para:
                    print(f"Valor mínimo é {op.min_para} (ou all-in com 't').")
                    continue
                return Acao(AUMENTAR, valor)
            else:
                print("Comando não reconhecido. Digite ? para ajuda.")
