"""Poker Cash Game — Texas Hold'em No-Limit para treino pessoal.

Uso:  python main.py            (menu no terminal)
      python main.py --web      (interface no navegador)
      python main.py --help     (todas as opções)
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import webbrowser

from poker.cartas import configurar_simbolos
from poker.cenarios import CENARIOS, jogar_cenario
from poker.config import DIFICULDADES, MAX_BOTS, MIN_BOTS, NOME_DIFICULDADE, Configuracao
from poker.estatisticas import diagnostico, fmt
from poker.interface import EntradaEncerrada, InterfaceTerminal, ler
from poker.persistencia import Banco
from poker.quiz import corrigir, gerar_pergunta
from poker.ranges import ABERTURA, POSICOES, tabela_posicao
from poker.relatorio import relatorio_html, relatorio_texto
from poker.sessao import SessaoCash

PASTA_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")


# ------------------------------------------------------------------ perguntas
def perguntar_int(texto: str, padrao: int, minimo: int, maximo: int) -> int:
    while True:
        resp = ler(f"{texto} [{padrao}]: ").strip()
        if not resp:
            return padrao
        try:
            valor = int(resp)
        except ValueError:
            print("Digite um número inteiro.")
            continue
        if minimo <= valor <= maximo:
            return valor
        print(f"Valor deve ficar entre {minimo} e {maximo}.")


def perguntar_sn(texto: str, padrao: bool) -> bool:
    resp = ler(f"{texto} [{'S/n' if padrao else 's/N'}]: ").strip().lower()
    if not resp:
        return padrao
    return resp.startswith("s")


def configurar_partida(base: Configuracao) -> Configuracao:
    print("\n--- Nova partida (Enter mantém o valor entre colchetes) ---")
    bb = perguntar_int("Big blind", base.big_blind, 2, 1_000_000)
    sb = perguntar_int("Small blind", min(base.small_blind, bb), 1, bb)
    fichas = perguntar_int("Fichas iniciais", max(base.fichas_iniciais, bb * 2), bb * 2, 100_000_000)
    bots = perguntar_int(f"Quantidade de bots ({MIN_BOTS}-{MAX_BOTS})", base.num_bots, MIN_BOTS, MAX_BOTS)
    ante = perguntar_int("Ante (0 = sem ante)", min(base.ante, bb), 0, bb)
    straddle = perguntar_sn(f"Straddle obrigatório de {bb * 2} à esquerda do big blind?", base.straddle)
    opcoes = " / ".join(f"{i + 1}={NOME_DIFICULDADE[d]}" for i, d in enumerate(DIFICULDADES))
    idx = perguntar_int(f"Dificuldade dos bots ({opcoes})", DIFICULDADES.index(base.dificuldade) + 1, 1, 3)
    treinador = perguntar_sn("Ativar o treinador (comentários nas suas decisões)?", base.treinador)
    cfg = Configuracao(fichas, bots, sb, bb, base.repor_bots, ante, straddle, DIFICULDADES[idx - 1], treinador)
    cfg.validar()
    return cfg


# ------------------------------------------------------------------ cash game
def jogar_sessao(sessao: SessaoCash, ui: InterfaceTerminal) -> None:
    ui.saindo = False
    ui.treinador = sessao.cfg.treinador
    mesa = sessao.mesa
    voce = sessao.humano
    print(f"\nSessão #{sessao.sessao_id} — {sessao.cfg.resumo()}")
    print("Na mesa: " + ", ".join(
        f"{j.nome} ({j.fichas})" + (f" [{j.estrategia.estilo}]" if j.estrategia else "")
        for j in mesa.sentados()))
    if sessao.caminhos_historico:
        print(f"Histórico de mãos: {sessao.caminhos_historico[0]}")

    pausou = False
    while True:
        resultado, msgs = sessao.jogar_mao()
        if resultado is None:
            print("\nNão há adversários com fichas. Você limpou a mesa!")
            break
        print("\nFichas: " + " | ".join(f"{j.nome} {j.fichas}" for j in mesa.sentados()))
        print(f"Conferência: {resultado.total_depois} fichas na mesa; "
              f"esperado {resultado.total_esperado} → {'OK' if resultado.ok else 'ERRO'}")
        for m in msgs:
            print(m)
        if ui.saindo:
            break
        try:
            if voce.fichas == 0:
                if not perguntar_sn(f"Você ficou sem fichas. Recomprar {sessao.cfg.fichas_iniciais}?", False):
                    break
                sessao.recomprar()
            else:
                resp = ler("[Enter] próxima mão | [s] sair da mesa | [p] pausar e salvar: ").strip().lower()
                if resp == "s":
                    break
                if resp == "p":
                    pausou = True
                    break
        except EntradaEncerrada:
            ui.saindo = True
            break

    if pausou:
        sessao.pausar()
        print(f"\nMesa salva. Use 'Continuar mesa salva' no menu para voltar "
              f"(você tem {voce.fichas} fichas; comprou {voce.comprado}).")
        return
    r = sessao.encerrar()
    e = r["estatisticas"]
    print("\n=== Você saiu da mesa ===")
    print(f"Mãos jogadas: {r['maos']}")
    print(f"Fichas compradas: {r['comprado']} | Saiu com: {r['saida']} | Resultado: {r['resultado']:+d}")
    if r["maos"]:
        print(f"bb/100: {fmt(e['bb100'], 1, '')} | VPIP {fmt(e['vpip'])} | PFR {fmt(e['pfr'])} | "
              f"3-bet {fmt(e['tres_bet'])} | WTSD {fmt(e['wtsd'])} | W$SD {fmt(e['wsd'])}")
    print(f"Conferência final: {r['fichas_na_mesa']} fichas seguem na mesa com os bots; "
          f"esperado {r['esperado']} → {'OK' if r['conferencia_ok'] else 'ERRO'}")
    if r["nuvem"]:
        print(r["nuvem"])


# ------------------------------------------------------------------ outros modos
def menu_cenarios(ui: InterfaceTerminal, rng: random.Random) -> None:
    print("\n--- Cenários de prática ---")
    for i, c in enumerate(CENARIOS, 1):
        print(f"  {i}. {c.titulo}")
    idx = perguntar_int("Escolha o cenário (0 = voltar)", 1, 0, len(CENARIOS))
    if idx == 0:
        return
    c = CENARIOS[idx - 1]
    print(f"\n### {c.titulo}\n{c.descricao}")
    ui.saindo, ui.treinador = False, True
    mesa, res = jogar_cenario(c, ui.decidir, print, rng=rng)
    voce = mesa.humano
    print(f"\nResultado: {res.resultados.get(voce.nome, 0):+d} fichas "
          f"(conferência {'OK' if res.ok else 'ERRO'})")
    print(f"\nAnálise: {c.analise}")


def menu_quiz(banco: Banco, rng: random.Random) -> None:
    n = perguntar_int("\nQuantas perguntas", 10, 1, 100)
    acertos = 0
    erros = []
    for i in range(1, n + 1):
        p = gerar_pergunta(rng)
        print(f"\n{i}/{n}. {p.enunciado()}")
        while True:
            resp = ler("> ").strip().lower()
            if resp[:1] in ("a", "d"):
                break
            print("Responda 'a' (aumentar) ou 'd' (desistir).")
        if corrigir(p, resp):
            acertos += 1
            print("✔ Certo. " + p.explicacao())
        else:
            erros.append(p)
            print("✘ Errado. " + p.explicacao())
    banco.registrar_quiz(acertos, n)
    print(f"\nResultado: {acertos}/{n} ({100 * acertos / n:.0f}%).")
    if erros:
        print("Revise: " + ", ".join(f"{p.classe} no {p.posicao}" for p in erros))


def menu_tabelas() -> None:
    print("\nPosições: " + ", ".join(f"{i + 1}={p}" for i, p in enumerate(POSICOES)))
    idx = perguntar_int("Qual posição (0 = resumo de todas)", 7, 0, len(POSICOES))
    if idx == 0:
        for p in POSICOES:
            print(f"  {p:<6} abre o top {ABERTURA[p]:.0f}% das mãos")
        return
    print("\n" + tabela_posicao(POSICOES[idx - 1]))


def menu_estatisticas(banco: Banco, pasta: str) -> None:
    print("\n" + relatorio_texto(banco))
    caminho = relatorio_html(banco, os.path.join(pasta, "relatorio.html"))
    print(f"\nRelatório completo com gráficos: {caminho}")
    if perguntar_sn("Abrir no navegador?", False):
        webbrowser.open("file://" + os.path.abspath(caminho))


# ------------------------------------------------------------------ principal
def main(argv=None) -> int:
    padrao = Configuracao()
    p = argparse.ArgumentParser(description="Poker cash game (Texas Hold'em No-Limit) para treino.")
    p.add_argument("--fichas", type=int, default=padrao.fichas_iniciais, help="fichas iniciais padrão")
    p.add_argument("--bots", type=int, default=padrao.num_bots, help="quantidade de bots padrão")
    p.add_argument("--sb", type=int, default=padrao.small_blind, help="small blind")
    p.add_argument("--bb", type=int, default=padrao.big_blind, help="big blind")
    p.add_argument("--ante", type=int, default=padrao.ante, help="ante (0 = sem ante)")
    p.add_argument("--straddle", action="store_true", help="straddle obrigatório (2x BB)")
    p.add_argument("--dificuldade", choices=DIFICULDADES, default=padrao.dificuldade)
    p.add_argument("--sem-treinador", action="store_true", help="desliga os comentários do treinador")
    p.add_argument("--nao-repor-bots", action="store_true", help="bots que quebram não são substituídos")
    p.add_argument("--semente", type=int, default=None, help="semente aleatória (reproduz partidas)")
    p.add_argument("--sem-simbolos", action="store_true", help="usa e/c/o/p em vez de ♠♥♦♣")
    p.add_argument("--dados", default=PASTA_PADRAO, help="pasta do banco, históricos e relatórios")
    p.add_argument("--web", action="store_true", help="abre a interface no navegador")
    p.add_argument("--porta", type=int, default=8765, help="porta da interface web")
    p.add_argument("--sem-navegador", action="store_true", help="não abre o navegador automaticamente")
    args = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    configurar_simbolos(not args.sem_simbolos)

    base = Configuracao(args.fichas, args.bots, args.sb, args.bb, not args.nao_repor_bots,
                        args.ante, args.straddle, args.dificuldade, not args.sem_treinador)
    try:
        base.validar()
    except ValueError as e:
        print(f"Configuração inválida: {e}")
        return 2

    if args.web:
        from poker.web.servidor import servir
        servir(args.dados, args.porta, abrir_navegador=not args.sem_navegador, base=base,
               semente=args.semente)
        return 0

    rng = random.Random(args.semente)
    banco = Banco(os.path.join(args.dados, "poker.db"))
    ui = InterfaceTerminal(random.Random(rng.random()))
    print("=" * 60)
    print(" POKER CASH GAME — Texas Hold'em No-Limit (treino)")
    print(" Digite ? durante sua vez para ver os comandos.")
    print("=" * 60)
    try:
        while True:
            salva = banco.mesa_salva()
            print("\n--- Menu ---")
            print("  1. Nova partida (cash game)")
            print("  2. Continuar mesa salva" + (f" (salva em {salva['salvo_em'][:16].replace('T', ' ')})"
                                                   if salva else " (nenhuma)"))
            print("  3. Cenários de prática")
            print("  4. Quiz pré-flop")
            print("  5. Tabelas de mãos iniciais por posição")
            print("  6. Estatísticas e evolução")
            print("  7. Interface web")
            print("  0. Sair")
            op = ler("Opção [1]: ").strip() or "1"
            if op == "0":
                break
            if op == "1":
                cfg = configurar_partida(base)
                jogar_sessao(SessaoCash(banco, args.dados, rng, ui.decidir, cfg, observador=print), ui)
            elif op == "2":
                if salva is None:
                    print("Não há mesa salva.")
                    continue
                jogar_sessao(SessaoCash(banco, args.dados, rng, ui.decidir, observador=print,
                                        continuar=True), ui)
            elif op == "3":
                menu_cenarios(ui, rng)
            elif op == "4":
                menu_quiz(banco, rng)
            elif op == "5":
                menu_tabelas()
            elif op == "6":
                menu_estatisticas(banco, args.dados)
            elif op == "7":
                from poker.web.servidor import servir
                banco.fechar()
                servir(args.dados, args.porta, abrir_navegador=not args.sem_navegador, base=base,
                       semente=args.semente)
                banco = Banco(os.path.join(args.dados, "poker.db"))
            else:
                print("Opção inválida.")
            if ui.saindo:
                break
    except (EntradaEncerrada, KeyboardInterrupt):
        print("\nEncerrado.")
    banco.fechar()
    print("Até a próxima!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
