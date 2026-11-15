"""Sincronização OPCIONAL das sessões com o Supabase (desligada por padrão).

O jogo funciona 100% offline com o SQLite local. Para ter uma cópia das suas
sessões na nuvem (por exemplo, para ver o histórico em outro computador):

1. Crie um projeto no Supabase e rode ``supabase/schema.sql`` no SQL Editor.
2. Crie ``dados/nuvem.json`` com::

       {"url": "https://SEU-PROJETO.supabase.co", "chave": "SUA_SECRET_KEY"}

   ou defina as variáveis de ambiente ``SUPABASE_URL`` e ``SUPABASE_KEY``.
   Use a chave secreta (service role) só neste arquivo local, que está no
   .gitignore; a tabela tem RLS ativado e não aceita a chave pública.

Usa só ``urllib`` da biblioteca padrão.
"""
from __future__ import annotations

import json
import os
import platform
import urllib.error
import urllib.request
from typing import Optional, Tuple

from .estatisticas import resumir
from .persistencia import Banco

TABELA = "sessoes_poker"


def carregar_config(pasta_dados: str) -> Optional[dict]:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    caminho = os.path.join(pasta_dados, "nuvem.json")
    if (not url or not chave) and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
        url, chave = d.get("url"), d.get("chave")
    if url and chave:
        return {"url": url.rstrip("/"), "chave": chave}
    return None


def montar_registro(banco: Banco, sessao_id: int) -> dict:
    s = banco.sessao(sessao_id)
    r = resumir(banco.maos(sessao_id))
    return {
        "dispositivo": platform.node() or "desconhecido",
        "id_local": sessao_id,
        "inicio": s["inicio"], "fim": s["fim"], "origem": s["origem"],
        "config": json.loads(s["config"]),
        "big_blind": s["big_blind"], "comprado": s["comprado"], "saida": s["saida"],
        "maos": s["maos"], "resultado": s["resultado"],
        "bb100": r["bb100"], "vpip": r["vpip"], "pfr": r["pfr"], "tres_bet": r["tres_bet"],
        "wtsd": r["wtsd"], "wsd": r["wsd"], "af": r["af"],
    }


def enviar_sessao(cfg: dict, registro: dict, timeout: float = 10) -> Tuple[bool, str]:
    url = f"{cfg['url']}/rest/v1/{TABELA}?on_conflict=dispositivo,id_local"
    req = urllib.request.Request(
        url, data=json.dumps(registro).encode("utf-8"), method="POST",
        headers={"apikey": cfg["chave"], "Authorization": f"Bearer {cfg['chave']}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"sem conexão ({e})"


def sincronizar_pendentes(banco: Banco, pasta_dados: str) -> Optional[str]:
    """Envia as sessões ainda não sincronizadas. Devolve uma mensagem ou None se desligado."""
    cfg = carregar_config(pasta_dados)
    if cfg is None:
        return None
    enviadas, erros = 0, []
    for s in banco.sessoes():
        if s["sincronizada"] or not s["maos"]:
            continue
        ok, msg = enviar_sessao(cfg, montar_registro(banco, s["id"]))
        if ok:
            if s["fim"]:
                banco.marcar_sincronizada(s["id"])
            enviadas += 1
        else:
            erros.append(msg)
            break
    if erros:
        return f"Supabase: falha ao sincronizar ({erros[0]}). Os dados continuam salvos localmente."
    return f"Supabase: {enviadas} sessão(ões) sincronizada(s)."
