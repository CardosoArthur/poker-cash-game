"""Interface web: sobe o servidor numa porta livre e joga mãos pela API HTTP."""
import json
import os
import threading
import time
import unittest
import urllib.request

from poker.web.servidor import criar_servidor
from tests.auxiliares import PastaTemporaria


class TestWeb(unittest.TestCase):
    def setUp(self):
        self._pasta = PastaTemporaria()
        self.pasta = self._pasta.__enter__()
        self.srv, self.ctrl = criar_servidor(self.pasta, porta=0, semente=3)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.ctrl.banco.fechar()
        self._pasta.__exit__()

    def get(self, caminho):
        with urllib.request.urlopen(self.url + caminho, timeout=10) as r:
            corpo = r.read().decode("utf-8")
            return json.loads(corpo) if r.headers.get_content_type() == "application/json" else corpo

    def post(self, caminho, dados):
        req = urllib.request.Request(self.url + caminho, json.dumps(dados).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def esperar(self, condicao, limite=30):
        fim = time.time() + limite
        while time.time() < fim:
            e = self.get("/api/estado")
            if condicao(e):
                return e
            time.sleep(0.02)
        self.fail("tempo esgotado esperando o servidor")

    def test_pagina_e_partida_completa_pela_api(self):
        self.assertIn("Poker Cash Game", self.get("/"))
        r = self.post("/api/iniciar", {"fichas_iniciais": 600, "num_bots": 3, "small_blind": 5,
                                       "big_blind": 10, "ante": 1, "straddle": True,
                                       "dificuldade": "medio", "treinador": True})
        self.assertTrue(r["ok"], r)
        self.assertFalse(self.post("/api/iniciar", {})["ok"])  # já existe partida

        maos = 0
        while maos < 6:
            e = self.esperar(lambda e: e["aguardando"] in ("acao", "entre_maos", "recompra", "config"))
            if e["aguardando"] == "acao":
                op = e["opcoes"]
                self.assertTrue(self.get("/api/equity")["ok"])
                self.assertFalse(self.post("/api/acao", {"tipo": "aumentar", "valor": 1})["ok"]
                                 if op["pode_aumentar"] and op["min_para"] > 1 else False)
                tipo = "passar" if op["pode_passar"] else "pagar"
                self.assertTrue(self.post("/api/acao", {"tipo": tipo})["ok"])
            elif e["aguardando"] in ("entre_maos", "recompra"):
                maos += 1
                m = e["mesa"]
                self.assertEqual(m["conferencia"]["total"], m["conferencia"]["esperado"])
                cmd = "recomprar" if e["aguardando"] == "recompra" else ("proxima" if maos < 6 else "sair")
                self.assertTrue(self.post("/api/comando", {"comando": cmd})["ok"])
            else:
                break

        e = self.esperar(lambda e: e["aguardando"] == "config" and e["resumo_final"])
        r = e["resumo_final"]
        self.assertTrue(r["conferencia_ok"])
        self.assertEqual(r["maos"], 6)
        log = "\n".join(self.get("/api/estado")["log"])
        self.assertIn("[Treinador]", log)
        self.assertIn("straddle", log)
        self.assertIn("<svg", self.get("/relatorio"))
        self.assertTrue(os.path.exists(os.path.join(self.pasta, "poker.db")))

    def test_pausar_e_continuar(self):
        self.assertTrue(self.post("/api/iniciar", {"num_bots": 2})["ok"])
        while True:
            e = self.esperar(lambda e: e["aguardando"] in ("acao", "entre_maos", "recompra"))
            if e["aguardando"] == "acao":
                self.post("/api/acao", {"tipo": "desistir"})
            else:
                break
        self.post("/api/comando", {"comando": "pausar"})
        e = self.esperar(lambda e: e["aguardando"] == "config")
        self.assertTrue(e["tem_mesa_salva"])
        self.assertTrue(self.post("/api/iniciar", {"continuar": True})["ok"])
        e = self.esperar(lambda e: e["mesa"].get("mao", 0) >= 2)
        self.assertEqual(e["mesa"]["mao"], 2)  # continua a numeração da mesa salva


if __name__ == "__main__":
    unittest.main()
