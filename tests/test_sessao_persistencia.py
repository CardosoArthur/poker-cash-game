"""Sessões salvas no SQLite, pausar/continuar, relatório e sincronização opcional."""
import json
import os
import random
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from poker.config import Configuracao
from poker.nuvem import sincronizar_pendentes
from poker.persistencia import Banco
from poker.relatorio import grafico_ascii, relatorio_html, relatorio_texto
from poker.sessao import SessaoCash
from tests.auxiliares import PastaTemporaria, sempre_paga


class TestSessao(unittest.TestCase):
    def test_jogar_pausar_continuar_e_encerrar(self):
        with PastaTemporaria() as pasta:
            banco = Banco(os.path.join(pasta, "poker.db"))
            cfg = Configuracao(fichas_iniciais=500, num_bots=3, ante=1, dificuldade="medio")
            s = SessaoCash(banco, pasta, random.Random(1), sempre_paga, cfg)
            for _ in range(8):
                res, _ = s.jogar_mao()
                self.assertTrue(res.ok)
                if s.humano.fichas == 0:
                    s.recomprar()
            fichas_antes = {j.nome: j.fichas for j in s.mesa.sentados()}
            s.pausar()
            self.assertIsNotNone(banco.mesa_salva())

            s2 = SessaoCash(banco, pasta, random.Random(2), sempre_paga, continuar=True)
            self.assertEqual(s2.sessao_id, s.sessao_id)
            self.assertEqual({j.nome: j.fichas for j in s2.mesa.sentados()}, fichas_antes)
            self.assertIsNone(banco.mesa_salva())
            self.assertEqual(s2.maos_jogadas, 8)
            for _ in range(5):
                res, _ = s2.jogar_mao()
                self.assertTrue(res.ok)
                if s2.humano.fichas == 0:
                    s2.recomprar()
            r = s2.encerrar()
            self.assertTrue(r["conferencia_ok"])
            self.assertEqual(r["maos"], 13)

            sessao = banco.sessao(s.sessao_id)
            self.assertIsNotNone(sessao["fim"])
            maos = banco.maos(s.sessao_id)
            self.assertEqual(len(maos), 13)
            # o resultado da sessão é a soma dos resultados mão a mão
            self.assertEqual(sum(m.resultado for m in maos), sessao["resultado"])
            self.assertEqual(sessao["resultado"], r["saida"] - r["comprado"])
            curva = banco.curva_resultado()
            self.assertEqual(len(curva), 13)
            self.assertEqual(curva[-1]["fichas"], sessao["resultado"])

            # históricos nos dois formatos; a sessão continuada grava no mesmo arquivo
            self.assertEqual(s.caminhos_historico, s2.caminhos_historico)
            pt, ps = s.caminhos_historico
            with open(ps, encoding="utf-8") as f:
                self.assertEqual(f.read().count("PokerStars Hand #"), 13)
            with open(pt, encoding="utf-8") as f:
                self.assertEqual(f.read().count("=== Mão #"), 13)

            texto = relatorio_texto(banco)
            self.assertIn("VPIP", texto)
            caminho = relatorio_html(banco, os.path.join(pasta, "relatorio.html"))
            with open(caminho, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("<svg", html)
            self.assertIn("Estatísticas por posição", html)
            banco.fechar()

    def test_quiz_registrado(self):
        with PastaTemporaria() as pasta:
            banco = Banco(os.path.join(pasta, "p.db"))
            banco.registrar_quiz(7, 10)
            self.assertIn("7/10", relatorio_texto(banco))
            banco.fechar()

    def test_grafico_ascii(self):
        g = grafico_ascii([0, 5, -3, 10], largura=10, altura=4)
        self.assertEqual(len(g.splitlines()), 5)
        self.assertEqual(g.count("●"), 4)


class _Receptor(BaseHTTPRequestHandler):
    recebidos = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers["Content-Length"]))
        _Receptor.recebidos.append((self.path, {k.lower(): v for k, v in self.headers.items()},
                                    json.loads(corpo)))
        self.send_response(201)
        self.end_headers()


class TestNuvem(unittest.TestCase):
    def test_desligada_sem_configuracao(self):
        with PastaTemporaria() as pasta:
            banco = Banco(os.path.join(pasta, "p.db"))
            antigo = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_KEY")}
            try:
                self.assertIsNone(sincronizar_pendentes(banco, pasta))
            finally:
                for k, v in antigo.items():
                    if v is not None:
                        os.environ[k] = v
            banco.fechar()

    def test_envia_sessao_para_api_rest(self):
        srv = HTTPServer(("127.0.0.1", 0), _Receptor)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with PastaTemporaria() as pasta:
                with open(os.path.join(pasta, "nuvem.json"), "w") as f:
                    json.dump({"url": f"http://127.0.0.1:{srv.server_address[1]}", "chave": "chave-teste"}, f)
                banco = Banco(os.path.join(pasta, "poker.db"))
                s = SessaoCash(banco, pasta, random.Random(1), sempre_paga,
                               Configuracao(num_bots=2), historico=False)
                for _ in range(3):
                    s.jogar_mao()
                r = s.encerrar()
                self.assertIn("1 sessão", r["nuvem"])
                caminho, cab, corpo = _Receptor.recebidos[-1]
                self.assertEqual(caminho, "/rest/v1/sessoes_poker?on_conflict=dispositivo,id_local")
                self.assertEqual(cab["apikey"], "chave-teste")
                self.assertEqual(cab["authorization"], "Bearer chave-teste")
                self.assertEqual(corpo["maos"], 3)
                self.assertEqual(corpo["resultado"], r["resultado"])
                self.assertEqual(banco.sessao(s.sessao_id)["sincronizada"], 1)
                banco.fechar()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
