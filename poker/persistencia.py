"""Banco de dados local (SQLite, já incluso no Python).

Guarda as sessões, as estatísticas de cada mão sua, a mesa salva (para continuar
depois) e os resultados do quiz. O arquivo fica em ``dados/poker.db``.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from .estatisticas import EstatMao

ESQUEMA = """
CREATE TABLE IF NOT EXISTS sessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL,
    fim TEXT,
    origem TEXT NOT NULL DEFAULT 'cash',
    config TEXT NOT NULL,
    big_blind INTEGER NOT NULL,
    comprado INTEGER NOT NULL DEFAULT 0,
    saida INTEGER,
    maos INTEGER NOT NULL DEFAULT 0,
    resultado INTEGER NOT NULL DEFAULT 0,
    sincronizada INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS maos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL REFERENCES sessoes(id),
    numero INTEGER NOT NULL,
    data TEXT NOT NULL,
    posicao TEXT NOT NULL,
    big_blind INTEGER NOT NULL,
    resultado INTEGER NOT NULL,
    vpip INTEGER NOT NULL, pfr INTEGER NOT NULL,
    oport_3bet INTEGER NOT NULL, fez_3bet INTEGER NOT NULL,
    viu_flop INTEGER NOT NULL, showdown INTEGER NOT NULL, ganhou_showdown INTEGER NOT NULL,
    agressoes_pos INTEGER NOT NULL, pagamentos_pos INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_maos_sessao ON maos(sessao_id);
CREATE TABLE IF NOT EXISTS mesa_salva (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    sessao_id INTEGER NOT NULL,
    dados TEXT NOT NULL,
    salvo_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    acertos INTEGER NOT NULL,
    total INTEGER NOT NULL
);
"""

_CAMPOS_MAO = ["vpip", "pfr", "oport_3bet", "fez_3bet", "viu_flop", "showdown",
               "ganhou_showdown", "agressoes_pos", "pagamentos_pos"]


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Banco:
    def __init__(self, caminho: str):
        self.caminho = caminho
        pasta = os.path.dirname(caminho)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()

    # ------------------------------------------------------------ sessões
    def nova_sessao(self, config: dict, origem: str = "cash") -> int:
        cur = self.con.execute(
            "INSERT INTO sessoes (inicio, origem, config, big_blind) VALUES (?, ?, ?, ?)",
            (_agora(), origem, json.dumps(config), config.get("big_blind", 10)))
        self.con.commit()
        return cur.lastrowid

    def atualizar_sessao(self, sessao_id: int, comprado: int, fichas_atuais: int, maos: int) -> None:
        self.con.execute("UPDATE sessoes SET comprado=?, saida=?, maos=?, resultado=? WHERE id=?",
                         (comprado, fichas_atuais, maos, fichas_atuais - comprado, sessao_id))
        self.con.commit()

    def encerrar_sessao(self, sessao_id: int, comprado: int, saida: int, maos: int) -> None:
        self.con.execute("UPDATE sessoes SET fim=?, comprado=?, saida=?, maos=?, resultado=? WHERE id=?",
                         (_agora(), comprado, saida, maos, saida - comprado, sessao_id))
        self.con.commit()

    def sessoes(self) -> List[sqlite3.Row]:
        return list(self.con.execute("SELECT * FROM sessoes ORDER BY id"))

    def sessao(self, sessao_id: int) -> Optional[sqlite3.Row]:
        return self.con.execute("SELECT * FROM sessoes WHERE id=?", (sessao_id,)).fetchone()

    def marcar_sincronizada(self, sessao_id: int) -> None:
        self.con.execute("UPDATE sessoes SET sincronizada=1 WHERE id=?", (sessao_id,))
        self.con.commit()

    # ------------------------------------------------------------ mãos
    def registrar_mao(self, sessao_id: int, e: EstatMao) -> None:
        self.con.execute(
            "INSERT INTO maos (sessao_id, numero, data, posicao, big_blind, resultado, "
            + ", ".join(_CAMPOS_MAO) + ") VALUES (?, ?, ?, ?, ?, ?" + ", ?" * len(_CAMPOS_MAO) + ")",
            (sessao_id, e.numero, _agora(), e.posicao, e.big_blind, e.resultado,
             *[int(getattr(e, c)) for c in _CAMPOS_MAO]))
        self.con.commit()

    def maos(self, sessao_id: Optional[int] = None) -> List[EstatMao]:
        sql = "SELECT * FROM maos" + (" WHERE sessao_id=?" if sessao_id else "") + " ORDER BY id"
        linhas = self.con.execute(sql, (sessao_id,) if sessao_id else ())
        saida = []
        for r in linhas:
            e = EstatMao(nome="Você", posicao=r["posicao"], big_blind=r["big_blind"], numero=r["numero"],
                         resultado=r["resultado"])
            for c in _CAMPOS_MAO:
                v = r[c]
                setattr(e, c, bool(v) if c not in ("agressoes_pos", "pagamentos_pos") else v)
            saida.append(e)
        return saida

    def curva_resultado(self) -> List[dict]:
        """Resultado acumulado mão a mão (fichas e big blinds), para o gráfico."""
        acum = acum_bb = 0.0
        pontos = []
        for r in self.con.execute("SELECT sessao_id, resultado, big_blind FROM maos ORDER BY id"):
            acum += r["resultado"]
            acum_bb += r["resultado"] / r["big_blind"]
            pontos.append({"sessao": r["sessao_id"], "fichas": acum, "bb": acum_bb})
        return pontos

    # ------------------------------------------------------------ mesa salva
    def salvar_mesa(self, sessao_id: int, dados: dict) -> None:
        self.con.execute("INSERT OR REPLACE INTO mesa_salva (id, sessao_id, dados, salvo_em) VALUES (1, ?, ?, ?)",
                         (sessao_id, json.dumps(dados), _agora()))
        self.con.commit()

    def mesa_salva(self) -> Optional[dict]:
        r = self.con.execute("SELECT * FROM mesa_salva WHERE id=1").fetchone()
        if r is None:
            return None
        return {"sessao_id": r["sessao_id"], "dados": json.loads(r["dados"]), "salvo_em": r["salvo_em"]}

    def apagar_mesa_salva(self) -> None:
        self.con.execute("DELETE FROM mesa_salva")
        self.con.commit()

    # ------------------------------------------------------------ quiz
    def registrar_quiz(self, acertos: int, total: int) -> None:
        self.con.execute("INSERT INTO quiz (data, acertos, total) VALUES (?, ?, ?)", (_agora(), acertos, total))
        self.con.commit()

    def historico_quiz(self) -> List[sqlite3.Row]:
        return list(self.con.execute("SELECT * FROM quiz ORDER BY id"))
