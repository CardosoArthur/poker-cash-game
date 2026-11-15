"""Interface web: um servidor HTTP local (biblioteca padrão) que reaproveita o
mesmo motor do terminal. O motor roda numa thread; quando é a sua vez, ele
espera a ação enviada pelo navegador.

    python main.py --web           ->  http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import os
import queue
import random
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ..acoes import ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao
from ..bots import estimar_equity
from ..config import Configuracao
from ..narrador import Narrador
from ..persistencia import Banco
from ..relatorio import relatorio_html
from ..sessao import SessaoCash
from ..treinador import comentar

PASTA_ESTATICA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def carta_json(c) -> dict:
    return {"v": {10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}.get(c.valor, str(c.valor)), "n": c.naipe}


class ControladorWeb:
    def __init__(self, pasta_dados: str, base: Optional[Configuracao] = None, semente: Optional[int] = None):
        self.pasta = pasta_dados
        self.base = base or Configuracao()
        self.rng = random.Random(semente)
        self.banco = Banco(os.path.join(pasta_dados, "poker.db"))
        self.lock = threading.RLock()
        self.log: list = []
        self.aguardando = "config"
        self.opcoes: Optional[dict] = None
        self.vez: Optional[str] = None
        self.mostradas: dict = {}
        self.snapshot: dict = {}
        self.resumo_final: Optional[dict] = None
        self.respostas: "queue.Queue" = queue.Queue()
        self.sessao: Optional[SessaoCash] = None
        self.thread: Optional[threading.Thread] = None
        self.erro: Optional[str] = None
        self._estado_decisao = None
        self._narrador = Narrador(self._registrar_log)

    # ------------------------------------------------------------ eventos do motor
    def _registrar_log(self, txt: str) -> None:
        with self.lock:
            self.log.append(txt)

    def _ouvinte(self, ev: dict) -> None:
        if ev["tipo"] == "inicio_mao":
            self.mostradas = {}
        if ev["tipo"] == "showdown":
            self.mostradas[ev["nome"]] = [carta_json(c) for c in ev["cartas"]]
        self._narrador(ev)
        self._atualizar_snapshot()

    def _atualizar_snapshot(self) -> None:
        s = self.sessao
        if s is None:
            return
        m = s.mesa
        jogadores = []
        for k, j in enumerate(m.assentos):
            if j is None:
                continue
            ver = j.humano or j.nome in self.mostradas
            jogadores.append({
                "assento": k, "nome": j.nome, "fichas": j.fichas, "aposta": j.aposta_rodada,
                "posicao": j.posicao, "botao": k == m.botao, "desistiu": j.desistiu, "all_in": j.all_in,
                "em_jogo": j.em_jogo, "humano": j.humano, "vez": j.nome == self.vez,
                "estilo": getattr(j.estrategia, "estilo", None),
                "cartas": ([carta_json(c) for c in j.cartas] if ver else
                           [None] * len(j.cartas) if j.em_jogo and not j.desistiu else []),
            })
        with self.lock:
            self.snapshot = {
                "mao": m.num_mao, "rodada": m.rodada,
                "comunitarias": [carta_json(c) for c in m.comunitarias],
                "pote": sum(j.contribuicao for j in m.sentados() if j.em_jogo),
                "jogadores": jogadores, "config": m.cfg.para_dict(), "resumo_config": m.cfg.resumo(),
                "sessao_id": s.sessao_id,
                "conferencia": {"total": m.total_fichas(), "esperado": m.total_esperado()},
            }

    def _decisor(self, j, estado, op) -> Acao:
        with self.lock:
            self.vez = j.nome
            self.opcoes = asdict(op)
            self._estado_decisao = (list(j.cartas), estado, op)
            self.aguardando = "acao"
        self._atualizar_snapshot()
        acao = self.respostas.get()
        if self.sessao and self.sessao.cfg.treinador:
            self._registrar_log(str(comentar(j.cartas, estado, op, acao, self.rng)))
        with self.lock:
            self.aguardando = None
            self.opcoes = None
            self.vez = None
        return acao

    def _laco(self) -> None:
        s = self.sessao
        try:
            while True:
                res, msgs = s.jogar_mao()
                if res is None:
                    self._registrar_log("Não há adversários com fichas. Você limpou a mesa!")
                    break
                self._registrar_log(f"Conferência: {res.total_depois} fichas na mesa; esperado "
                                    f"{res.total_esperado} → {'OK' if res.ok else 'ERRO'}")
                for msg in msgs:
                    self._registrar_log(msg)
                self._atualizar_snapshot()
                with self.lock:
                    self.aguardando = "recompra" if s.humano.fichas == 0 else "entre_maos"
                cmd = self.respostas.get()
                with self.lock:
                    self.aguardando = None
                if cmd == "recomprar" and s.humano.fichas == 0:
                    s.recomprar()
                    self._registrar_log(f"Você recomprou {s.cfg.fichas_iniciais} fichas.")
                    continue
                if cmd == "pausar":
                    s.pausar()
                    self._registrar_log("Mesa salva. Escolha 'Continuar mesa salva' para voltar.")
                    with self.lock:
                        self.resumo_final = {"pausada": True}
                    return
                if cmd != "proxima":
                    break
            r = s.encerrar()
            self._registrar_log(f"Você saiu da mesa: comprou {r['comprado']}, saiu com {r['saida']} "
                                f"({r['resultado']:+d}).")
            if r.get("nuvem"):
                self._registrar_log(r["nuvem"])
            with self.lock:
                self.resumo_final = {k: v for k, v in r.items() if k != "estatisticas"}
                self.resumo_final["estatisticas"] = r["estatisticas"]
        except Exception as e:  # mostra erros do motor na página em vez de travar
            with self.lock:
                self.erro = f"{type(e).__name__}: {e}"
            self._registrar_log(f"ERRO: {self.erro}")
        finally:
            with self.lock:
                self.aguardando = "config"
                self.vez = None

    # ------------------------------------------------------------ API
    def iniciar(self, dados: dict) -> dict:
        with self.lock:
            if self.aguardando != "config":
                return {"ok": False, "erro": "Já existe uma partida em andamento."}
            continuar = bool(dados.get("continuar"))
            try:
                cfg = None
                if not continuar:
                    base = self.base.para_dict()
                    base.update({k: v for k, v in dados.items() if k in base})
                    cfg = Configuracao.de_dict(base)
                    cfg.fichas_iniciais, cfg.num_bots = int(cfg.fichas_iniciais), int(cfg.num_bots)
                    cfg.small_blind, cfg.big_blind, cfg.ante = int(cfg.small_blind), int(cfg.big_blind), int(cfg.ante)
                    cfg.straddle, cfg.treinador = bool(cfg.straddle), bool(cfg.treinador)
                    cfg.validar()
                self.sessao = SessaoCash(self.banco, self.pasta, self.rng, self._decisor, cfg,
                                         ouvintes=[self._ouvinte], continuar=continuar)
            except (ValueError, TypeError) as e:
                return {"ok": False, "erro": str(e)}
            self.log.append(f"Sessão #{self.sessao.sessao_id} — {self.sessao.cfg.resumo()}")
            self.aguardando = None
            self.resumo_final = None
            self.erro = None
            self.respostas = queue.Queue()
        self._atualizar_snapshot()
        self.thread = threading.Thread(target=self._laco, daemon=True)
        self.thread.start()
        return {"ok": True}

    def acao(self, dados: dict) -> dict:
        with self.lock:
            if self.aguardando != "acao":
                return {"ok": False, "erro": "Não é a sua vez."}
            tipo = dados.get("tipo")
            if tipo not in (DESISTIR, PASSAR, PAGAR, AUMENTAR, ALL_IN):
                return {"ok": False, "erro": "Ação inválida."}
            op = self.opcoes
            para = int(dados.get("valor") or 0)
            if tipo == AUMENTAR:
                if not op["pode_aumentar"]:
                    return {"ok": False, "erro": "Aumentar não é permitido agora."}
                if para >= op["max_para"]:
                    tipo = ALL_IN
                elif para < op["min_para"]:
                    return {"ok": False, "erro": f"O mínimo é {op['min_para']}."}
            if tipo == PASSAR and not op["pode_passar"]:
                return {"ok": False, "erro": "Há aposta a pagar."}
            self.aguardando = None
        self.respostas.put(Acao(tipo, para))
        return {"ok": True}

    def comando(self, dados: dict) -> dict:
        cmd = dados.get("comando")
        with self.lock:
            if self.aguardando not in ("entre_maos", "recompra") or \
                    cmd not in ("proxima", "sair", "pausar", "recomprar"):
                return {"ok": False, "erro": "Comando indisponível agora."}
            self.aguardando = None
        self.respostas.put(cmd)
        return {"ok": True}

    def equity(self) -> dict:
        with self.lock:
            if self.aguardando != "acao" or self._estado_decisao is None:
                return {"ok": False, "erro": "Disponível apenas na sua vez."}
            cartas, estado, op = self._estado_decisao
        eq = estimar_equity(cartas, estado.comunitarias, estado.num_oponentes, self.rng, 1500)
        odds = op.para_pagar / (estado.pote + op.para_pagar) if op.para_pagar else None
        return {"ok": True, "equity": eq, "pot_odds": odds, "oponentes": estado.num_oponentes}

    def estado(self, desde: int = 0) -> dict:
        with self.lock:
            return {
                "aguardando": self.aguardando, "opcoes": self.opcoes,
                "log": self.log[desde:], "total_log": len(self.log),
                "mesa": self.snapshot, "resumo_final": self.resumo_final, "erro": self.erro,
                "tem_mesa_salva": self.banco.mesa_salva() is not None if self.aguardando == "config" else False,
                "padrao": self.base.para_dict(),
            }


def _criar_handler(ctrl: ControladorWeb):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencia o log de cada requisição
            pass

        def _json(self, obj, status=200):
            corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _arquivo(self, caminho, tipo):
            with open(caminho, "rb") as f:
                corpo = f.read()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._arquivo(os.path.join(PASTA_ESTATICA, "index.html"), "text/html; charset=utf-8")
            if u.path == "/api/estado":
                desde = int(parse_qs(u.query).get("desde", ["0"])[0] or 0)
                return self._json(ctrl.estado(desde))
            if u.path == "/api/equity":
                return self._json(ctrl.equity())
            if u.path == "/relatorio":
                with ctrl.lock:
                    caminho = relatorio_html(ctrl.banco, os.path.join(ctrl.pasta, "relatorio.html"))
                return self._arquivo(caminho, "text/html; charset=utf-8")
            self._json({"erro": "não encontrado"}, 404)

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            try:
                dados = json.loads(self.rfile.read(tamanho) or b"{}")
            except json.JSONDecodeError:
                return self._json({"ok": False, "erro": "JSON inválido"}, 400)
            rotas = {"/api/iniciar": ctrl.iniciar, "/api/acao": ctrl.acao, "/api/comando": ctrl.comando}
            f = rotas.get(urlparse(self.path).path)
            if f is None:
                return self._json({"erro": "não encontrado"}, 404)
            self._json(f(dados))

    return Handler


def criar_servidor(pasta_dados: str, porta: int = 8765, base: Optional[Configuracao] = None,
                   semente: Optional[int] = None):
    ctrl = ControladorWeb(pasta_dados, base, semente)
    srv = ThreadingHTTPServer(("127.0.0.1", porta), _criar_handler(ctrl))
    srv.daemon_threads = True
    return srv, ctrl


def servir(pasta_dados: str, porta: int = 8765, abrir_navegador: bool = True,
           base: Optional[Configuracao] = None, semente: Optional[int] = None) -> None:
    srv, ctrl = criar_servidor(pasta_dados, porta, base, semente)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Interface web em {url}  (Ctrl+C para encerrar)")
    if abrir_navegador:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        srv.server_close()
        ctrl.banco.fechar()
