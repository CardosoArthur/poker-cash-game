"""Relatórios: estatísticas, evolução do saldo (gráfico) e dicas.

Saídas: texto para o terminal (com gráfico ASCII) e uma página HTML
autocontida com gráfico SVG (``dados/relatorio.html``), sem dependências.
"""
from __future__ import annotations

import html
import os
from typing import List, Sequence

from .estatisticas import diagnostico, fmt, resumir, resumir_por_posicao
from .persistencia import Banco
from .ranges import POSICOES

COLUNAS = [("maos", "Mãos", lambda v: str(v)), ("vpip", "VPIP", fmt), ("pfr", "PFR", fmt),
           ("tres_bet", "3-bet", fmt), ("wtsd", "WTSD", fmt), ("wsd", "W$SD", fmt),
           ("af", "AF", lambda v: fmt(v, 1, "")), ("bb100", "bb/100", lambda v: fmt(v, 1, ""))]


def grafico_ascii(valores: Sequence[float], largura: int = 60, altura: int = 12) -> str:
    if not valores:
        return "(sem mãos registradas ainda)"
    valores = list(valores)
    if len(valores) > largura:
        passo = len(valores) / largura
        valores = [valores[min(len(valores) - 1, int((i + 1) * passo) - 1)] for i in range(largura)]
    vmin, vmax = min(min(valores), 0.0), max(max(valores), 0.0)
    if vmax == vmin:
        vmax = vmin + 1
    def linha_de(v): return round((v - vmin) / (vmax - vmin) * altura)
    zero = linha_de(0.0)
    idx = [linha_de(v) for v in valores]
    saida = []
    for nivel in range(altura, -1, -1):
        y = vmin + (vmax - vmin) * nivel / altura
        cel = "".join("●" if i == nivel else ("─" if nivel == zero else " ") for i in idx)
        saida.append(f"{y:>9.1f} │{cel}")
    return "\n".join(saida)


def tabela_estatisticas(linhas: List[tuple]) -> str:
    cab = f"{'':<8}" + "".join(f"{t:>9}" for _, t, _ in COLUNAS)
    out = [cab]
    for rotulo, r in linhas:
        out.append(f"{rotulo:<8}" + "".join(f"{f(r[k]):>9}" for k, _, f in COLUNAS))
    return "\n".join(out)


def _linhas_posicao(maos) -> List[tuple]:
    por_pos = resumir_por_posicao(maos)
    return [(p, por_pos[p]) for p in POSICOES if p in por_pos]


def relatorio_texto(banco: Banco) -> str:
    maos = banco.maos()
    r = resumir(maos)
    sessoes = [s for s in banco.sessoes() if s["maos"]]
    partes = ["=== Suas estatísticas (todas as sessões) ===",
              f"Mãos: {r['maos']} | Resultado: {r['resultado']:+d} fichas "
              f"({r['resultado_bb']:+.1f} bb) | bb/100: {fmt(r['bb100'], 1, '')}",
              "", tabela_estatisticas([("Total", r)] + _linhas_posicao(maos)),
              "", "Evolução do resultado (big blinds acumulados):",
              grafico_ascii([p["bb"] for p in banco.curva_resultado()]),
              "", "Sessões:"]
    for s in sessoes[-10:]:
        estado = "em andamento" if not s["fim"] else "encerrada"
        partes.append(f"  #{s['id']:<3} {s['inicio'][:16].replace('T', ' ')}  {s['maos']:>4} mãos  "
                      f"{s['resultado']:+7d} fichas  ({s['origem']}, {estado})")
    quiz = banco.historico_quiz()
    if quiz:
        ac = sum(q["acertos"] for q in quiz)
        tot = sum(q["total"] for q in quiz)
        partes.append(f"\nQuiz pré-flop: {ac}/{tot} acertos ({100 * ac / tot:.0f}%) em {len(quiz)} rodada(s)")
    partes.append("\nDicas:")
    partes += [f"  • {d}" for d in diagnostico(r)]
    return "\n".join(partes)


def _svg_linha(pontos: List[dict], chave: str, largura: int = 820, altura: int = 260) -> str:
    if not pontos:
        return "<p>Sem mãos registradas ainda.</p>"
    vals = [0.0] + [p[chave] for p in pontos]
    vmin, vmax = min(vals + [0]), max(vals + [0])
    if vmax == vmin:
        vmax = vmin + 1
    m = 44
    def x(i): return m + (largura - m - 10) * i / max(1, len(vals) - 1)
    def y(v): return 10 + (altura - 40) * (1 - (v - vmin) / (vmax - vmin))
    caminho = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    marcas = []
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4
        marcas.append(f'<line x1="{m}" x2="{largura - 10}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grade"/>'
                      f'<text x="{m - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
    # separadores de sessão
    seps = []
    for i in range(1, len(pontos)):
        if pontos[i]["sessao"] != pontos[i - 1]["sessao"]:
            seps.append(f'<line x1="{x(i + 1):.1f}" x2="{x(i + 1):.1f}" y1="10" y2="{altura - 30}" class="sessao"/>')
    cor = "#1a7f4b" if vals[-1] >= 0 else "#c0392b"
    return (f'<svg viewBox="0 0 {largura} {altura}" role="img" aria-label="Resultado acumulado">'
            + "".join(marcas) + "".join(seps)
            + f'<line x1="{m}" x2="{largura - 10}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="zero"/>'
            + f'<path d="{caminho}" fill="none" stroke="{cor}" stroke-width="2"/>'
            + f'<text x="{largura / 2}" y="{altura - 8}" text-anchor="middle">mãos ({len(pontos)})</text>'
            + "</svg>")


def relatorio_html(banco: Banco, caminho: str) -> str:
    maos = banco.maos()
    r = resumir(maos)
    pontos = banco.curva_resultado()

    def tabela(linhas):
        cab = "".join(f"<th>{html.escape(t)}</th>" for _, t, _ in COLUNAS)
        corpo = "".join("<tr><th>" + html.escape(rot) + "</th>"
                        + "".join(f"<td>{html.escape(f(rr[k]))}</td>" for k, _, f in COLUNAS) + "</tr>"
                        for rot, rr in linhas)
        return f"<table><tr><th></th>{cab}</tr>{corpo}</table>"

    sessoes = "".join(
        f"<tr><td>#{s['id']}</td><td>{html.escape(s['inicio'][:16].replace('T', ' '))}</td>"
        f"<td>{html.escape(s['origem'])}</td><td>{s['maos']}</td>"
        f"<td class='{'pos' if s['resultado'] >= 0 else 'neg'}'>{s['resultado']:+d}</td>"
        f"<td>{'encerrada' if s['fim'] else 'em andamento'}</td></tr>"
        for s in reversed(banco.sessoes()) if s["maos"])
    dicas = "".join(f"<li>{html.escape(d)}</li>" for d in diagnostico(r))
    cor = "pos" if r["resultado"] >= 0 else "neg"
    doc = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Relatório de treino — Poker</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,Segoe UI,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d2433;background:#f6f7f9}}
h1{{font-size:1.5rem}} h2{{font-size:1.1rem;margin-top:28px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap}} .card{{background:#fff;border-radius:10px;padding:12px 16px;box-shadow:0 1px 3px #0001;min-width:140px}}
.card b{{display:block;font-size:1.4rem}} .pos{{color:#1a7f4b}} .neg{{color:#c0392b}}
table{{border-collapse:collapse;background:#fff;width:100%;border-radius:8px;overflow:hidden}}
th,td{{padding:6px 10px;text-align:right;border-bottom:1px solid #eee}} th:first-child{{text-align:left}}
svg{{width:100%;background:#fff;border-radius:10px}} svg text{{font-size:11px;fill:#667}}
.grade{{stroke:#eee}} .zero{{stroke:#999;stroke-dasharray:4 3}} .sessao{{stroke:#cfd6e4;stroke-dasharray:2 4}}
</style></head><body>
<h1>Relatório de treino — Poker Cash Game</h1>
<div class="cards">
<div class="card">Mãos<b>{r['maos']}</b></div>
<div class="card">Resultado<b class="{cor}">{r['resultado']:+d}</b>fichas</div>
<div class="card">Em big blinds<b class="{cor}">{r['resultado_bb']:+.1f}</b>bb</div>
<div class="card">bb/100<b class="{cor}">{fmt(r['bb100'], 1, '')}</b></div>
</div>
<h2>Evolução do resultado (big blinds acumulados)</h2>
{_svg_linha(pontos, 'bb')}
<h2>Evolução do resultado (fichas acumuladas)</h2>
{_svg_linha(pontos, 'fichas')}
<h2>Estatísticas por posição</h2>
{tabela([("Total", r)] + _linhas_posicao(maos))}
<p><small>VPIP: entra no pote voluntariamente · PFR: aumenta no pré-flop · 3-bet: reaumenta contra uma abertura ·
WTSD: vai ao showdown após ver o flop · W$SD: ganha no showdown · AF: (apostas+aumentos)/pagamentos pós-flop.</small></p>
<h2>Dicas</h2><ul>{dicas}</ul>
<h2>Sessões</h2>
<table><tr><th>Sessão</th><th>Início</th><th>Tipo</th><th>Mãos</th><th>Resultado</th><th>Status</th></tr>{sessoes}</table>
</body></html>"""
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(doc)
    return caminho
