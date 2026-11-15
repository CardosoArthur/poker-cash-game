"""Estatísticas de jogo calculadas a partir dos eventos da mesa.

Definições (as mesmas usadas por trackers como PokerTracker/HM):
- VPIP: % de mãos em que o jogador colocou fichas voluntariamente no pré-flop
  (pagar ou aumentar; postar blinds não conta).
- PFR: % de mãos em que aumentou no pré-flop.
- 3-bet: % de vezes que aumentou quando enfrentava exatamente um aumento no pré-flop.
- WTSD: % das vezes que foi ao showdown depois de ver o flop.
- W$SD: % dos showdowns em que ganhou fichas.
- AF (fator de agressão pós-flop): (apostas + aumentos) / pagamentos.
- bb/100: resultado em big blinds a cada 100 mãos.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List, Optional


@dataclass
class EstatMao:
    nome: str
    posicao: str
    big_blind: int
    numero: int = 0
    vpip: bool = False
    pfr: bool = False
    oport_3bet: bool = False
    fez_3bet: bool = False
    viu_flop: bool = False
    showdown: bool = False
    ganhou_showdown: bool = False
    agressoes_pos: int = 0
    pagamentos_pos: int = 0
    resultado: int = 0  # variação de fichas na mão

    def para_dict(self) -> dict:
        return asdict(self)


def _pct(a: int, b: int) -> Optional[float]:
    return (100.0 * a / b) if b else None


def resumir(maos: Iterable[EstatMao]) -> dict:
    maos = list(maos)
    n = len(maos)
    viu_flop = sum(m.viu_flop for m in maos)
    sd = sum(m.showdown for m in maos)
    oport = sum(m.oport_3bet for m in maos)
    agr = sum(m.agressoes_pos for m in maos)
    pag = sum(m.pagamentos_pos for m in maos)
    resultado = sum(m.resultado for m in maos)
    em_bb = sum(m.resultado / m.big_blind for m in maos if m.big_blind)
    return {
        "maos": n,
        "vpip": _pct(sum(m.vpip for m in maos), n),
        "pfr": _pct(sum(m.pfr for m in maos), n),
        "tres_bet": _pct(sum(m.fez_3bet for m in maos), oport),
        "viu_flop": _pct(viu_flop, n),
        "wtsd": _pct(sd, viu_flop),
        "wsd": _pct(sum(m.ganhou_showdown for m in maos), sd),
        "af": (agr / pag) if pag else (float(agr) if agr else None),
        "resultado": resultado,
        "resultado_bb": em_bb,
        "bb100": (em_bb / n * 100) if n else None,
    }


def resumir_por_posicao(maos: Iterable[EstatMao]) -> Dict[str, dict]:
    grupos: Dict[str, List[EstatMao]] = defaultdict(list)
    for m in maos:
        grupos[m.posicao].append(m)
    return {p: resumir(ms) for p, ms in grupos.items()}


def fmt(v: Optional[float], casas: int = 0, sufixo: str = "%") -> str:
    if v is None:
        return "—"
    return f"{v:.{casas}f}{sufixo}"


def diagnostico(r: dict) -> List[str]:
    """Dicas simples a partir das estatísticas (vazamentos comuns)."""
    dicas = []
    if r["maos"] < 30:
        return ["Jogue pelo menos 30 mãos para as estatísticas começarem a dizer algo."]
    vpip, pfr = r["vpip"] or 0, r["pfr"] or 0
    if vpip > 35:
        dicas.append(f"VPIP {vpip:.0f}% está alto: você entra em mãos demais. Mesas 6-max costumam ficar entre 20% e 28%.")
    elif vpip < 15:
        dicas.append(f"VPIP {vpip:.0f}% está baixo: você pode estar desistindo de mãos lucrativas, principalmente no botão e no cutoff.")
    if vpip and pfr / vpip < 0.6:
        dicas.append(f"PFR ({pfr:.0f}%) bem abaixo do VPIP ({vpip:.0f}%): você paga mais do que aumenta. Prefira entrar no pote aumentando.")
    if r["tres_bet"] is not None and r["tres_bet"] < 4:
        dicas.append("3-bet baixo: aumente mais contra aberturas, principalmente em posição.")
    if r["wtsd"] is not None and r["wtsd"] > 35:
        dicas.append(f"WTSD {r['wtsd']:.0f}%: você vai ao showdown com frequência; cuidado para não pagar demais no river.")
    if r["wsd"] is not None and r["wtsd"] and r["wsd"] < 45:
        dicas.append(f"W$SD {r['wsd']:.0f}%: perde a maioria dos showdowns; as mãos com que chega ao fim estão fracas.")
    if r["af"] is not None and r["af"] < 1:
        dicas.append(f"Fator de agressão {r['af']:.1f}: jogo pós-flop passivo. Aposte mais as mãos fortes e os draws.")
    if not dicas:
        dicas.append("Nenhum vazamento óbvio nas estatísticas básicas. Continue revisando as mãos grandes.")
    return dicas


class Rastreador:
    """Ouvinte de eventos da mesa que monta as estatísticas de cada jogador."""

    def __init__(self):
        self.atual: Dict[str, EstatMao] = {}
        self.por_jogador: Dict[str, List[EstatMao]] = defaultdict(list)
        self.ao_fim: List[Callable[[Dict[str, EstatMao], dict], None]] = []

    def __call__(self, ev: dict) -> None:
        t = ev["tipo"]
        if t == "inicio_mao":
            self.atual = {nome: EstatMao(nome, ev["posicoes"][nome], ev["big_blind"], ev["numero"])
                          for _, nome, _ in ev["assentos"]}
        elif t == "acao":
            e = self.atual.get(ev["nome"])
            if e is None:
                return
            a = ev["acao"]
            if ev["rodada"] == "Pré-flop":
                if a in ("paga", "aumenta", "aposta"):
                    e.vpip = True
                if a in ("aumenta", "aposta"):
                    e.pfr = True
                if ev["aumentos_antes"] == 1:
                    e.oport_3bet = True
                    if a in ("aumenta", "aposta"):
                        e.fez_3bet = True
            else:
                if a in ("aposta", "aumenta"):
                    e.agressoes_pos += 1
                elif a == "paga":
                    e.pagamentos_pos += 1
        elif t == "rua" and ev["nome"] == "Flop":
            for nome in ev["vivos"]:
                if nome in self.atual:
                    self.atual[nome].viu_flop = True
        elif t == "showdown":
            if ev["nome"] in self.atual:
                self.atual[ev["nome"]].showdown = True
        elif t == "fim_mao":
            for nome, e in self.atual.items():
                e.resultado = ev["resultados"].get(nome, 0)
                if e.showdown and ev["ganhos"].get(nome, 0) > 0:
                    e.ganhou_showdown = True
                self.por_jogador[nome].append(e)
            for cb in self.ao_fim:
                cb(self.atual, ev)

    def resumo(self, nome: str) -> dict:
        return resumir(self.por_jogador.get(nome, []))

    def perfis(self) -> Dict[str, dict]:
        return {n: resumir(ms) for n, ms in self.por_jogador.items()}
