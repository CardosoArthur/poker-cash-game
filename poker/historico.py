"""Histórico de mãos em arquivo.

Dois formatos, ambos acrescentados mão a mão enquanto você joga:
- ``*_pt.txt``: texto em português, para ler e revisar;
- ``*_pokerstars.txt``: formato de histórico do PokerStars (em inglês, fichas
  de jogo), que ferramentas como PokerTracker 4, Hold'em Manager 3 e
  sites de replay conseguem importar. Seu nome aparece como o jogador da linha
  "Dealt to".
"""
from __future__ import annotations

import os
import time
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional

from .narrador import Narrador

_RANK = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
         10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}
_NOME_EN = {2: "Deuce", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
            9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen", 13: "King", 14: "Ace", 1: "Ace"}
_PLURAL_EN = {2: "Deuces", 3: "Threes", 4: "Fours", 5: "Fives", 6: "Sixes", 7: "Sevens",
              8: "Eights", 9: "Nines", 10: "Tens", 11: "Jacks", 12: "Queens", 13: "Kings", 14: "Aces"}


def carta_ps(c) -> str:
    return _RANK[c.valor] + c.naipe


def cartas_ps(cs) -> str:
    return " ".join(carta_ps(c) for c in cs)


def nome_ps(nome: str) -> str:
    """Nome sem acentos e sem espaços, como os conversores esperam."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return s.replace(" ", "_") or "Jogador"


def descrever_en(forca) -> str:
    cat, d = forca
    if cat == 8:
        return "a Royal Flush" if d[0] == 14 else f"a straight flush, {_NOME_EN[d[0] - 4]} to {_NOME_EN[d[0]]}"
    if cat == 7:
        return f"four of a kind, {_PLURAL_EN[d[0]]}"
    if cat == 6:
        return f"a full house, {_PLURAL_EN[d[0]]} full of {_PLURAL_EN[d[1]]}"
    if cat == 5:
        return f"a flush, {_NOME_EN[d[0]]} high"
    if cat == 4:
        return f"a straight, {_NOME_EN[d[0] - 4]} to {_NOME_EN[d[0]]}"
    if cat == 3:
        return f"three of a kind, {_PLURAL_EN[d[0]]}"
    if cat == 2:
        return f"two pair, {_PLURAL_EN[d[0]]} and {_PLURAL_EN[d[1]]}"
    if cat == 1:
        return f"a pair of {_PLURAL_EN[d[0]]}"
    return f"high card {_NOME_EN[d[0]]}"


def _acrescentar(caminho: str, texto: str) -> None:
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(texto)


class HistoricoTexto:
    """Histórico legível em português."""

    def __init__(self, caminho: str):
        self.caminho = caminho
        self.linhas: List[str] = []
        self._narrador = Narrador(self.linhas.append)

    def __call__(self, ev: dict) -> None:
        if ev["tipo"] == "inicio_mao":
            self.linhas.clear()
            self.linhas.append(f"[{ev['data']}]")
        if ev["tipo"] == "cartas" and not ev["humano"]:
            return
        self._narrador(ev)
        if ev["tipo"] == "fim_mao":
            fichas = " | ".join(f"{n} {v}" for n, v in ev["fichas"].items())
            self.linhas.append(f"Fichas após a mão: {fichas}")
            _acrescentar(self.caminho, "\n".join(self.linhas).lstrip("\n") + "\n\n")


class HistoricoPokerStars:
    """Histórico no formato do PokerStars (dinheiro de jogo)."""

    def __init__(self, caminho: str, nome_mesa: str = "Treino", max_assentos: int = 9,
                 id_base: Optional[int] = None):
        self.caminho = caminho
        self.nome_mesa = nome_mesa
        self.max_assentos = max_assentos
        self.id_base = id_base if id_base is not None else int(time.time()) * 1000
        self._reset()

    def _reset(self) -> None:
        self.l: List[str] = []
        self.assento: Dict[str, int] = {}
        self.botao: Optional[str] = None
        self.rua = "Pré-flop"
        self.cartas_vistas = False
        self.showdown = False
        self.mostradas: Dict[str, tuple] = {}
        self.desistiu_em: Dict[str, str] = {}
        self.ganhos: List[dict] = []
        self.colocou: Dict[str, int] = {}

    def __call__(self, ev: dict) -> None:
        t = ev["tipo"]
        n = nome_ps(ev["nome"]) if "nome" in ev and t not in ("rua",) else None
        if t == "inicio_mao":
            self._reset()
            data = datetime.fromisoformat(ev["data"])
            self.botao = nome_ps(ev["botao"])
            self.l.append(f"PokerStars Hand #{self.id_base + ev['numero']}:  Hold'em No Limit "
                          f"({ev['small_blind']}/{ev['big_blind']}) - {data:%Y/%m/%d %H:%M:%S} ET")
            self.l.append(f"Table '{self.nome_mesa}' {self.max_assentos}-max (Play Money) "
                          f"Seat #{ev['botao_assento']} is the button")
            for assento, nome, fichas in ev["assentos"]:
                self.assento[nome_ps(nome)] = assento
                self.l.append(f"Seat {assento}: {nome_ps(nome)} ({fichas} in chips)")
        elif t == "ante":
            self.l.append(f"{n}: posts the ante {ev['valor']}" + (" and is all-in" if ev["all_in"] else ""))
            self.colocou[n] = self.colocou.get(n, 0) + ev["valor"]
        elif t == "blind":
            tipo = {"small blind": "small blind", "big blind": "big blind"}.get(ev["blind"])
            txt = f"posts {tipo} {ev['valor']}" if tipo else f"posts straddle {ev['valor']}"
            self.l.append(f"{n}: {txt}" + (" and is all-in" if ev["all_in"] else ""))
            self.colocou[n] = self.colocou.get(n, 0) + ev["valor"]
        elif t == "cartas":
            if not self.cartas_vistas:
                self.cartas_vistas = True
                self.l.append("*** HOLE CARDS ***")
            if ev["humano"]:
                self.l.append(f"Dealt to {n} [{cartas_ps(ev['cartas'])}]")
        elif t == "acao":
            a = ev["acao"]
            sufixo = " and is all-in" if ev["all_in"] else ""
            if a == "desiste":
                txt = "folds"
                self.desistiu_em[n] = self.rua
            elif a == "passa":
                txt = "checks"
            elif a == "paga":
                txt = f"calls {ev['valor']}"
            elif a == "aposta":
                txt = f"bets {ev['valor']}"
            else:
                txt = f"raises {ev['incremento']} to {ev['para']}"
            self.colocou[n] = self.colocou.get(n, 0) + ev.get("valor", 0)
            self.l.append(f"{n}: {txt}{sufixo}")
        elif t == "rua":
            self.rua = ev["nome"]
            cs = ev["comunitarias"]
            if ev["nome"] == "Flop":
                self.l.append(f"*** FLOP *** [{cartas_ps(cs)}]")
            elif ev["nome"] == "Turn":
                self.l.append(f"*** TURN *** [{cartas_ps(cs[:3])}] [{carta_ps(cs[3])}]")
            else:
                self.l.append(f"*** RIVER *** [{cartas_ps(cs[:4])}] [{carta_ps(cs[4])}]")
        elif t == "devolucao":
            self.l.append(f"Uncalled bet ({ev['valor']}) returned to {n}")
        elif t == "showdown":
            if not self.showdown:
                self.showdown = True
                self.l.append("*** SHOW DOWN ***")
            self.mostradas[n] = (ev["cartas"], ev["forca"])
            self.l.append(f"{n}: shows [{cartas_ps(ev['cartas'])}] ({descrever_en(ev['forca'])})")
        elif t == "ganho":
            self.ganhos.append({"nome": n, "valor": ev["valor"], "rotulo": ev["rotulo"],
                                "showdown": ev["showdown"]})
        elif t == "pote":
            pass
        elif t == "fim_mao":
            self._fechar(ev)

    def _fechar(self, ev: dict) -> None:
        laterais = sorted({g["rotulo"] for g in self.ganhos if g["rotulo"].startswith("pote lateral")})

        def rotulo_ps(r: str) -> str:
            if r == "pote principal":
                return "main pot"
            if r.startswith("pote lateral"):
                return "side pot" if len(laterais) == 1 else f"side pot-{r.split()[-1]}"
            return "pot"

        if not self.showdown and self.ganhos:
            self.l.append(f"{self.ganhos[0]['nome']}: doesn't show hand")
        for g in self.ganhos:
            self.l.append(f"{g['nome']} collected {g['valor']} from {rotulo_ps(g['rotulo'])}")

        total = ev["pote_total"]
        por_pote: Dict[str, int] = {}
        for g in self.ganhos:
            por_pote[g["rotulo"]] = por_pote.get(g["rotulo"], 0) + g["valor"]
        self.l.append("*** SUMMARY ***")
        if "pote principal" in por_pote:
            partes = [f"Main pot {por_pote['pote principal']}."]
            for r in laterais:
                nome = "Side pot" if len(laterais) == 1 else f"Side pot-{r.split()[-1]}"
                partes.append(f"{nome} {por_pote[r]}.")
            self.l.append(f"Total pot {total} " + " ".join(partes) + " | Rake 0")
        else:
            self.l.append(f"Total pot {total} | Rake 0")
        if ev["comunitarias"]:
            self.l.append(f"Board [{cartas_ps(ev['comunitarias'])}]")
        ganhou: Dict[str, int] = {}
        for g in self.ganhos:
            ganhou[g["nome"]] = ganhou.get(g["nome"], 0) + g["valor"]
        quando = {"Pré-flop": "before Flop", "Flop": "on the Flop", "Turn": "on the Turn", "River": "on the River"}
        for nome, assento in sorted(self.assento.items(), key=lambda kv: kv[1]):
            marca = " (button)" if nome == self.botao else ""
            if nome in self.desistiu_em:
                r = self.desistiu_em[nome]
                nao_apostou = " (didn't bet)" if r == "Pré-flop" and not self.colocou.get(nome) else ""
                txt = f"folded {quando[r]}{nao_apostou}"
            elif nome in self.mostradas:
                cs, forca = self.mostradas[nome]
                if nome in ganhou:
                    txt = f"showed [{cartas_ps(cs)}] and won ({ganhou[nome]}) with {descrever_en(forca)}"
                else:
                    txt = f"showed [{cartas_ps(cs)}] and lost with {descrever_en(forca)}"
            elif nome in ganhou:
                txt = f"collected ({ganhou[nome]})"
            else:
                txt = "mucked"
            self.l.append(f"Seat {assento}: {nome}{marca} {txt}")
        _acrescentar(self.caminho, "\n".join(self.l) + "\n\n\n")


def criar_historicos(pasta: str, prefixo: str, id_base: Optional[int] = None):
    """Devolve (ouvintes, caminhos) para os dois formatos de histórico."""
    pt = os.path.join(pasta, f"{prefixo}_pt.txt")
    ps = os.path.join(pasta, f"{prefixo}_pokerstars.txt")
    return [HistoricoTexto(pt), HistoricoPokerStars(ps, id_base=id_base)], (pt, ps)
