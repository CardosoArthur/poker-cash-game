"""Converte os eventos da mesa em texto em português."""
from __future__ import annotations

from typing import Callable, Optional

from .cartas import formatar

_VERBO = {"desiste": "desiste", "passa": "passa", "paga": "paga"}


def texto_evento(ev: dict) -> Optional[str]:
    t = ev["tipo"]
    if t == "inicio_mao":
        extra = f", ante {ev['ante']}" if ev.get("ante") else ""
        return (f"\n=== Mão #{ev['numero']} — botão: {ev['botao']} "
                f"| blinds {ev['small_blind']}/{ev['big_blind']}{extra} ===")
    if t == "ante":
        return f"{ev['nome']} paga ante {ev['valor']}" + (" (all-in)" if ev["all_in"] else "")
    if t == "blind":
        return f"{ev['nome']} posta {ev['blind']} {ev['valor']}" + (" (all-in)" if ev["all_in"] else "")
    if t == "cartas":
        return f"Suas cartas: {formatar(ev['cartas'])}" if ev["humano"] else None
    if t == "acao":
        sufixo = " (all-in)" if ev["all_in"] else ""
        a = ev["acao"]
        if a in ("desiste", "passa"):
            return f"{ev['nome']} {a}"
        if a == "paga":
            return f"{ev['nome']} paga {ev['valor']}{sufixo}"
        if a == "aposta":
            return f"{ev['nome']} aposta {ev['para']}{sufixo}"
        return f"{ev['nome']} aumenta para {ev['para']}{sufixo}"
    if t == "rua":
        return f"--- {ev['nome']}: {formatar(ev['comunitarias'])}  (pote {ev['pote']})"
    if t == "showdown":
        return f"  {ev['nome']}: {formatar(ev['cartas'])} → {ev['descricao']}"
    if t == "devolucao":
        return f"  {ev['valor']} devolvido a {ev['nome']} (aposta não paga)"
    if t == "pote":
        rot = ev["rotulo"].capitalize()
        if len(ev["vencedores"]) == 1:
            return f"  {rot} ({ev['valor']}): {ev['vencedores'][0]} vence"
        partes = ", ".join(f"{n} +{v}" for n, v in ev["premios"].items())
        return f"  {rot} ({ev['valor']}): dividido — {partes}"
    if t == "ganho" and not ev["showdown"]:
        return f"{ev['nome']} leva o pote de {ev['valor']} (os outros desistiram)"
    if t == "recompra":
        return f"{ev['nome']} recompra {ev['valor']} fichas"
    return None


class Narrador:
    def __init__(self, saida: Callable[[str], None]):
        self.saida = saida
        self._showdown_anunciado = False

    def __call__(self, ev: dict) -> None:
        if ev["tipo"] == "inicio_mao":
            self._showdown_anunciado = False
        if ev["tipo"] == "showdown" and not self._showdown_anunciado:
            self._showdown_anunciado = True
            self.saida(f"--- Showdown — mesa: {formatar(ev['comunitarias'])}")
        txt = texto_evento(ev)
        if txt is not None:
            self.saida(txt)
