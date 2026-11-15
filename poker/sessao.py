"""Sessão de cash game: liga a mesa ao banco local, ao histórico de mãos e à
sincronização opcional. Usada pelo terminal e pela interface web."""
from __future__ import annotations

import os
import random
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from .config import Configuracao
from .estatisticas import resumir
from .historico import criar_historicos
from .mesa import Mesa, ResultadoMao
from .nuvem import sincronizar_pendentes
from .persistencia import Banco


class SessaoCash:
    def __init__(self, banco: Banco, pasta_dados: str, rng: random.Random, decisor_humano,
                 cfg: Optional[Configuracao] = None, observador: Optional[Callable[[str], None]] = None,
                 ouvintes: Optional[list] = None, continuar: bool = False, historico: bool = True):
        self.banco = banco
        self.pasta_dados = pasta_dados
        if continuar:
            salva = banco.mesa_salva()
            if salva is None:
                raise ValueError("Não há mesa salva para continuar.")
            self.sessao_id = salva["sessao_id"]
            self.mesa = Mesa.de_dict(salva["dados"], rng, decisor_humano=decisor_humano,
                                     observador=observador, ouvintes=ouvintes)
            banco.apagar_mesa_salva()
        else:
            assert cfg is not None
            self.mesa = Mesa(cfg, rng, decisor_humano=decisor_humano, observador=observador,
                             ouvintes=ouvintes)
            self.sessao_id = banco.nova_sessao(cfg.para_dict())
        self.cfg = self.mesa.cfg
        self.caminhos_historico: Tuple[str, ...] = ()
        if historico:
            prefixo = f"{datetime.now():%Y-%m-%d}_sessao{self.sessao_id:03d}"
            hist, self.caminhos_historico = criar_historicos(
                os.path.join(pasta_dados, "historico"), prefixo, id_base=self.sessao_id * 1_000_000)
            self.mesa.ouvintes.extend(hist)
        self.mesa.rastreador.ao_fim.append(self._registrar)
        self.maos_jogadas = len(banco.maos(self.sessao_id))
        self.encerrada = False

    @property
    def humano(self):
        return self.mesa.humano

    def _registrar(self, atual, ev) -> None:
        h = self.humano
        if h is None or h.nome not in atual:
            return
        self.banco.registrar_mao(self.sessao_id, atual[h.nome])
        self.maos_jogadas += 1
        self.banco.atualizar_sessao(self.sessao_id, h.comprado, h.fichas, self.maos_jogadas)

    def jogar_mao(self) -> Tuple[Optional[ResultadoMao], List[str]]:
        res = self.mesa.jogar_mao()
        msgs = self.mesa.repor_bots_quebrados() if res else []
        return res, msgs

    def recomprar(self) -> None:
        self.mesa.recomprar(self.humano, self.cfg.fichas_iniciais)
        self.banco.atualizar_sessao(self.sessao_id, self.humano.comprado, self.humano.fichas, self.maos_jogadas)

    def pausar(self) -> None:
        """Salva a mesa inteira (stacks dos bots, botão, compras) para continuar depois."""
        h = self.humano
        self.banco.atualizar_sessao(self.sessao_id, h.comprado, h.fichas, self.maos_jogadas)
        self.banco.salvar_mesa(self.sessao_id, self.mesa.para_dict())
        self.encerrada = True

    def encerrar(self) -> dict:
        """Você sai da mesa com as fichas que tem."""
        h = self.humano
        saida, comprado = h.fichas, h.comprado
        self.mesa.retirar(h)
        self.banco.encerrar_sessao(self.sessao_id, comprado, saida, self.maos_jogadas)
        self.encerrada = True
        r = resumir(self.banco.maos(self.sessao_id))
        nuvem = sincronizar_pendentes(self.banco, self.pasta_dados)
        return {"sessao_id": self.sessao_id, "comprado": comprado, "saida": saida,
                "resultado": saida - comprado, "maos": self.maos_jogadas, "estatisticas": r,
                "conferencia_ok": self.mesa.total_fichas() == self.mesa.total_esperado(),
                "fichas_na_mesa": self.mesa.total_fichas(), "esperado": self.mesa.total_esperado(),
                "nuvem": nuvem}
