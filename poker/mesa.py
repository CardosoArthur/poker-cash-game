"""Motor da mesa de cash game: antes, blinds, straddle, distribuição, rodadas
de apostas, showdown, potes e verificação de conservação de fichas.

A mesa não imprime nada: ela emite **eventos** (dicionários) para os ouvintes
registrados. O narrador (texto em português), o histórico de mãos, as
estatísticas e a interface web são todos ouvintes.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .acoes import (ALL_IN, AUMENTAR, DESISTIR, PAGAR, PASSAR, Acao, EstadoMao,
                    InfoJogador, Opcoes)
from .avaliador import avaliar, descrever
from .bots import ESTILOS, NOMES_BOTS, EstrategiaBot
from .cartas import Baralho, Carta
from .config import MAX_ASSENTOS, Configuracao
from .estatisticas import Rastreador
from .potes import calcular_potes, distribuir_potes
from .ranges import nomes_posicoes

Ouvinte = Callable[[dict], None]


class ErroConservacao(RuntimeError):
    """As fichas na mesa não batem com o total esperado."""


class Jogador:
    def __init__(self, nome: str, fichas: int, humano: bool = False, estrategia=None):
        self.nome = nome
        self.fichas = fichas
        self.humano = humano
        self.estrategia = estrategia
        self.comprado = fichas  # total de fichas que este jogador trouxe para a mesa
        self.reset_mao()

    def reset_mao(self) -> None:
        self.cartas: List[Carta] = []
        self.aposta_rodada = 0
        self.contribuicao = 0
        self.desistiu = False
        self.all_in = False
        self.agiu = False
        self.pode_aumentar = True
        self.em_jogo = False
        self.posicao = ""

    def __repr__(self) -> str:
        return f"Jogador({self.nome!r}, {self.fichas})"


@dataclass
class ResultadoMao:
    numero: int
    total_antes: int
    total_depois: int
    total_esperado: int
    ganhos: Dict[str, int] = field(default_factory=dict)
    resultados: Dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.total_antes == self.total_depois == self.total_esperado


Decisor = Callable[[Jogador, EstadoMao, Opcoes], Acao]


class Mesa:
    def __init__(self, cfg: Configuracao, rng: Optional[random.Random] = None,
                 decisor_humano: Optional[Decisor] = None,
                 observador: Optional[Callable[[str], None]] = None,
                 nome_humano: str = "Você",
                 jogadores: Optional[List[Jogador]] = None,
                 ouvintes: Optional[List[Ouvinte]] = None):
        if jogadores is None:
            cfg.validar()
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.decisor_humano = decisor_humano
        self.ouvintes: List[Ouvinte] = []
        self.rastreador = Rastreador()
        self.ouvintes.append(self.rastreador)
        if observador is not None:
            from .narrador import Narrador
            self.ouvintes.append(Narrador(observador))
        self.ouvintes.extend(ouvintes or [])

        self.assentos: List[Optional[Jogador]] = [None] * MAX_ASSENTOS
        self.botao = -1
        self.num_mao = 0
        self.total_comprado = 0
        self.total_retirado = 0
        self.comunitarias: List[Carta] = []
        self.rodada = ""
        self.aposta_atual = 0
        self.min_inc = cfg.big_blind
        self.aumentos = 0
        self.agressor: Optional[str] = None
        self.agressor_preflop: Optional[str] = None
        self.entrou_preflop: Dict[str, str] = {}
        self._nomes_usados: set = set()

        if jogadores is not None:
            for i, j in enumerate(jogadores):
                self.sentar(j, i)
        else:
            if decisor_humano is not None:
                self.sentar(Jogador(nome_humano, cfg.fichas_iniciais, humano=True), 0)
            for _ in range(cfg.num_bots):
                self.sentar(self.criar_bot())

    # ------------------------------------------------------------ eventos
    def emitir(self, tipo: str, **dados) -> None:
        ev = {"tipo": tipo, "mao": self.num_mao, **dados}
        for o in list(self.ouvintes):
            o(ev)

    # ------------------------------------------------------------ assentos
    @property
    def humano(self) -> Optional[Jogador]:
        return next((j for j in self.assentos if j and j.humano), None)

    def sentados(self) -> List[Jogador]:
        return [j for j in self.assentos if j is not None]

    def criar_bot(self, nome: Optional[str] = None, estilo: Optional[str] = None,
                  fichas: Optional[int] = None) -> Jogador:
        if nome is None:
            livres = [n for n in NOMES_BOTS if n not in self._nomes_usados]
            nome = self.rng.choice(livres) if livres else f"Bot{len(self._nomes_usados) + 1}"
        estilo = estilo or self.rng.choice(list(ESTILOS))
        estrategia = EstrategiaBot(random.Random(self.rng.random()), estilo, self.cfg.dificuldade)
        return Jogador(nome, self.cfg.fichas_iniciais if fichas is None else fichas,
                       estrategia=estrategia)

    def sentar(self, jogador: Jogador, assento: Optional[int] = None) -> int:
        if assento is None:
            assento = self.assentos.index(None)
        if self.assentos[assento] is not None:
            raise ValueError("Assento ocupado.")
        self.assentos[assento] = jogador
        self._nomes_usados.add(jogador.nome)
        self.total_comprado += jogador.fichas
        jogador.comprado = jogador.fichas
        return assento

    def retirar(self, jogador: Jogador) -> int:
        """Jogador sai da mesa levando as fichas que tem (cash game)."""
        i = self.assentos.index(jogador)
        self.assentos[i] = None
        self.total_retirado += jogador.fichas
        return i

    def recomprar(self, jogador: Jogador, valor: int) -> None:
        jogador.fichas += valor
        jogador.comprado += valor
        self.total_comprado += valor
        self.emitir("recompra", nome=jogador.nome, valor=valor)

    def total_fichas(self) -> int:
        return sum(j.fichas for j in self.sentados())

    def total_esperado(self) -> int:
        return self.total_comprado - self.total_retirado

    def repor_bots_quebrados(self) -> List[str]:
        """Bots sem fichas saem; se configurado, outro bot senta no lugar."""
        msgs = []
        for i, j in enumerate(self.assentos):
            if j is not None and not j.humano and j.fichas == 0:
                self.retirar(j)
                msgs.append(f"{j.nome} ficou sem fichas e saiu da mesa.")
                if self.cfg.repor_bots:
                    novo = self.criar_bot()
                    self.sentar(novo, i)
                    msgs.append(f"{novo.nome} ({novo.estrategia.estilo}) sentou com {novo.fichas} fichas.")
        return msgs

    # ------------------------------------------------------------ salvar / restaurar
    def para_dict(self) -> dict:
        return {
            "cfg": self.cfg.para_dict(),
            "botao": self.botao,
            "num_mao": self.num_mao,
            "total_comprado": self.total_comprado,
            "total_retirado": self.total_retirado,
            "assentos": [None if j is None else {
                "nome": j.nome, "fichas": j.fichas, "comprado": j.comprado, "humano": j.humano,
                "estilo": getattr(j.estrategia, "estilo", None),
            } for j in self.assentos],
            "nomes_usados": sorted(self._nomes_usados),
        }

    @classmethod
    def de_dict(cls, d: dict, rng: Optional[random.Random] = None, **kw) -> "Mesa":
        cfg = Configuracao.de_dict(d["cfg"])
        mesa = cls(cfg, rng, jogadores=[], **kw)
        for i, s in enumerate(d["assentos"]):
            if s is None:
                continue
            if s["humano"]:
                j = Jogador(s["nome"], s["fichas"], humano=True)
            else:
                estilo = s["estilo"] if s["estilo"] in ESTILOS else None
                j = mesa.criar_bot(s["nome"], estilo, s["fichas"])
            j.comprado = s["comprado"]
            mesa.assentos[i] = j
        mesa.botao = d["botao"]
        mesa.num_mao = d["num_mao"]
        mesa.total_comprado = d["total_comprado"]
        mesa.total_retirado = d["total_retirado"]
        mesa._nomes_usados = set(d.get("nomes_usados", []))
        return mesa

    # ------------------------------------------------------------ utilidades
    def _proximo(self, idx: int, cond: Callable[[Jogador], bool]) -> int:
        for passo in range(1, MAX_ASSENTOS + 1):
            k = (idx + passo) % MAX_ASSENTOS
            j = self.assentos[k]
            if j is not None and cond(j):
                return k
        raise RuntimeError("Nenhum jogador encontrado.")

    def _na_mao(self) -> List[Jogador]:
        return [j for j in self.sentados() if j.em_jogo]

    def _vivos(self) -> List[Jogador]:
        return [j for j in self._na_mao() if not j.desistiu]

    def _pote(self) -> int:
        return sum(j.contribuicao for j in self._na_mao())

    def _colocar(self, j: Jogador, valor: int, morto: bool = False) -> int:
        """Põe fichas no pote. ``morto`` (ante) não conta como aposta da rodada."""
        valor = max(0, min(valor, j.fichas))
        j.fichas -= valor
        if not morto:
            j.aposta_rodada += valor
        j.contribuicao += valor
        if j.fichas == 0:
            j.all_in = True
        return valor

    def _ordem_a_partir_do_botao(self) -> List[int]:
        em_jogo = lambda j: j.em_jogo  # noqa: E731
        ordem = [self.botao]
        while len(ordem) < len(self._na_mao()):
            ordem.append(self._proximo(ordem[-1], em_jogo))
        return ordem

    def estado(self, para: Optional[Jogador] = None) -> EstadoMao:
        vivos = self._vivos()
        return EstadoMao(
            numero_mao=self.num_mao, rodada=self.rodada,
            comunitarias=list(self.comunitarias), pote=self._pote(),
            big_blind=self.cfg.big_blind,
            num_oponentes=len(vivos) - (1 if para in vivos else 0),
            jogadores=[InfoJogador(j.nome, j.fichas, j.aposta_rodada, j.desistiu,
                                   j.all_in, k == self.botao, j.posicao, j.contribuicao)
                       for k, j in enumerate(self.assentos) if j is not None and j.em_jogo],
            posicao=para.posicao if para else "",
            aumentos=self.aumentos, agressor=self.agressor,
            agressor_preflop=self.agressor_preflop,
            perfis=self.rastreador.perfis(),
            entrou_preflop=dict(self.entrou_preflop),
        )

    def opcoes(self, j: Jogador) -> Opcoes:
        falta = max(0, self.aposta_atual - j.aposta_rodada)
        max_para = j.aposta_rodada + j.fichas
        outros_ativos = any(o is not j and not o.all_in for o in self._vivos())
        pode_aumentar = j.pode_aumentar and outros_ativos and max_para > self.aposta_atual
        min_para = min(self.aposta_atual + self.min_inc, max_para)
        return Opcoes(pode_passar=(falta == 0), para_pagar=min(falta, j.fichas),
                      pode_aumentar=pode_aumentar, min_para=min_para, max_para=max_para,
                      aposta_atual=self.aposta_atual, ja_apostado=j.aposta_rodada)

    # ------------------------------------------------------------ mão
    def jogar_mao(self, baralho: Optional[Baralho] = None) -> Optional[ResultadoMao]:
        for j in self.sentados():
            j.reset_mao()
            j.em_jogo = j.fichas > 0
        if len(self._na_mao()) < 2:
            return None

        cfg = self.cfg
        self.num_mao += 1
        total_antes = self.total_fichas()
        fichas_inicio = {j.nome: j.fichas for j in self._na_mao()}
        em_jogo = lambda j: j.em_jogo  # noqa: E731
        self.botao = self._proximo(self.botao, em_jogo)
        ordem = self._ordem_a_partir_do_botao()
        for k, pos in zip(ordem, nomes_posicoes(len(ordem))):
            self.assentos[k].posicao = pos
        heads_up = len(ordem) == 2
        sb = self.botao if heads_up else ordem[1]
        bb = self._proximo(sb, em_jogo)
        self.comunitarias = []
        self.rodada = "Pré-flop"
        self.agressor_preflop = None
        self.entrou_preflop = {}
        baralho = baralho or Baralho(self.rng)

        self.emitir("inicio_mao", numero=self.num_mao, data=datetime.now().isoformat(timespec="seconds"),
                    botao=self.assentos[self.botao].nome, botao_assento=self.botao + 1,
                    small_blind=cfg.small_blind, big_blind=cfg.big_blind, ante=cfg.ante,
                    assentos=[(k + 1, j.nome, j.fichas) for k, j in enumerate(self.assentos)
                              if j is not None and j.em_jogo],
                    posicoes={j.nome: j.posicao for j in self._na_mao()},
                    humano=self.humano.nome if self.humano and self.humano.em_jogo else None)

        if cfg.ante:
            for k in ordem[1:] + ordem[:1]:
                j = self.assentos[k]
                v = self._colocar(j, cfg.ante, morto=True)
                self.emitir("ante", nome=j.nome, valor=v, all_in=j.all_in)

        for k, tipo, valor in ((sb, "small blind", cfg.small_blind), (bb, "big blind", cfg.big_blind)):
            j = self.assentos[k]
            v = self._colocar(j, valor)
            self.emitir("blind", nome=j.nome, blind=tipo, valor=v, all_in=j.all_in)

        aposta_inicial, min_inc, ultimo_obrigatorio = cfg.big_blind, cfg.big_blind, bb
        if cfg.straddle and len(ordem) >= 3:
            st = self._proximo(bb, em_jogo)
            j = self.assentos[st]
            if not j.all_in:
                v = self._colocar(j, cfg.valor_straddle)
                self.emitir("blind", nome=j.nome, blind="straddle", valor=v, all_in=j.all_in)
                aposta_inicial = min_inc = cfg.valor_straddle
                ultimo_obrigatorio = st

        # Distribui duas cartas, uma por vez, começando à esquerda do botão.
        distribuicao = ordem[1:] + ordem[:1]
        for _ in range(2):
            for k in distribuicao:
                self.assentos[k].cartas += baralho.distribuir(1)
        for k in distribuicao:
            j = self.assentos[k]
            self.emitir("cartas", nome=j.nome, cartas=list(j.cartas), humano=j.humano)

        self._rodada_apostas(self._proximo(ultimo_obrigatorio, em_jogo), aposta_inicial, min_inc)

        for nome, n in (("Flop", 3), ("Turn", 1), ("River", 1)):
            if len(self._vivos()) == 1:
                break
            baralho.distribuir(1)  # carta queimada
            novas = baralho.distribuir(n)
            self.comunitarias += novas
            self.rodada = nome
            self.emitir("rua", nome=nome, novas=novas, comunitarias=list(self.comunitarias),
                        pote=self._pote(), vivos=[j.nome for j in self._vivos()])
            podem_agir = [j for j in self._vivos() if not j.all_in]
            if len(podem_agir) >= 2:
                self._rodada_apostas(self._proximo(self.botao, lambda j: j in podem_agir), 0,
                                     cfg.big_blind)

        ganhos = self._resolver()
        resultados = {j.nome: j.fichas - fichas_inicio[j.nome] for j in self._na_mao()}
        resultado = ResultadoMao(self.num_mao, total_antes, self.total_fichas(),
                                 self.total_esperado(), ganhos, resultados)
        self.emitir("fim_mao", numero=self.num_mao, ganhos=ganhos, resultados=resultados,
                    fichas={j.nome: j.fichas for j in self.sentados()},
                    comunitarias=list(self.comunitarias), pote_total=sum(ganhos.values()),
                    total=resultado.total_depois, esperado=resultado.total_esperado, ok=resultado.ok)
        if not resultado.ok:
            raise ErroConservacao(
                f"Mão #{self.num_mao}: fichas antes={total_antes}, depois={resultado.total_depois}, "
                f"esperado={resultado.total_esperado}")
        return resultado

    def _rodada_apostas(self, inicio: int, aposta_inicial: int, min_inc: int) -> None:
        self.aposta_atual = aposta_inicial
        self.min_inc = min_inc
        self.aumentos = 0
        self.agressor = None
        for j in self._na_mao():
            j.agiu = False
            j.pode_aumentar = True
        pos = inicio
        while True:
            vivos = self._vivos()
            if len(vivos) <= 1:
                break
            podem = [j for j in vivos if not j.all_in]
            pendentes = [j for j in podem if not j.agiu or j.aposta_rodada < self.aposta_atual]
            if not pendentes:
                break
            if len(podem) == 1 and podem[0].aposta_rodada >= self.aposta_atual:
                break  # todos os outros estão all-in e ele já cobriu
            k = pos
            while self.assentos[k] not in pendentes:
                k = (k + 1) % MAX_ASSENTOS
            j = self.assentos[k]
            self._aplicar(j, self._obter_acao(j))
            pos = (k + 1) % MAX_ASSENTOS
        for j in self.sentados():
            j.aposta_rodada = 0

    def _obter_acao(self, j: Jogador) -> Acao:
        op = self.opcoes(j)
        est = self.estado(j)
        if j.humano and self.decisor_humano is not None:
            return self.decisor_humano(j, est, op)
        if j.estrategia is None:
            return Acao(PASSAR if op.pode_passar else DESISTIR)
        return j.estrategia.decidir(j.cartas, est, op)

    def _aplicar(self, j: Jogador, acao: Acao) -> None:
        op = self.opcoes(j)
        tipo, para = acao.tipo, acao.para

        if tipo == ALL_IN:
            if op.pode_aumentar and op.max_para > self.aposta_atual:
                tipo, para = AUMENTAR, op.max_para
            else:
                tipo = PAGAR if op.para_pagar > 0 else PASSAR
        if tipo == PAGAR and op.para_pagar == 0:
            tipo = PASSAR
        if tipo == AUMENTAR:
            para = min(para, op.max_para)
            valido = op.pode_aumentar and para > self.aposta_atual and (
                para >= op.min_para or para == op.max_para)
            if not valido:
                tipo = PAGAR if op.para_pagar > 0 else PASSAR  # ação inválida vira pagar/passar
        if tipo == PASSAR and not op.pode_passar:
            tipo = DESISTIR

        base = dict(nome=j.nome, rodada=self.rodada, posicao=j.posicao,
                    aumentos_antes=self.aumentos, pote_antes=self._pote(),
                    para_pagar=op.para_pagar, humano=j.humano)
        if tipo == DESISTIR:
            j.desistiu = True
            self.emitir("acao", acao="desiste", valor=0, para=j.aposta_rodada, all_in=False, **base)
        elif tipo == PASSAR:
            self.emitir("acao", acao="passa", valor=0, para=j.aposta_rodada, all_in=False, **base)
        elif tipo == PAGAR:
            v = self._colocar(j, op.para_pagar)
            if self.rodada == "Pré-flop":
                self.entrou_preflop.setdefault(j.nome, "pagou")
            self.emitir("acao", acao="paga", valor=v, para=j.aposta_rodada, all_in=j.all_in, **base)
        else:  # AUMENTAR
            aposta_anterior = self.aposta_atual
            v = self._colocar(j, para - j.aposta_rodada)
            incremento = para - aposta_anterior
            verbo = "aposta" if aposta_anterior == 0 else "aumenta"
            self.emitir("acao", acao=verbo, valor=v, para=para, incremento=incremento,
                        all_in=j.all_in, **base)
            completo = incremento >= self.min_inc
            for o in self._vivos():
                if o is j:
                    continue
                if completo:
                    o.pode_aumentar = True
                elif o.agiu:
                    # All-in menor que um aumento mínimo não reabre a ação
                    # para quem já agiu: só pode pagar ou desistir.
                    o.pode_aumentar = False
                o.agiu = False
            if completo:
                self.min_inc = incremento
            self.aposta_atual = para
            self.aumentos += 1
            self.agressor = j.nome
            if self.rodada == "Pré-flop":
                self.agressor_preflop = j.nome
                self.entrou_preflop[j.nome] = "aumentou"
        j.agiu = True

    def _resolver(self) -> Dict[str, int]:
        vivos = self._vivos()
        na_mao = self._na_mao()
        ganhos: Dict[str, int] = {}
        por_nome = {j.nome: j for j in na_mao}

        if len(vivos) == 1:
            vencedor = vivos[0]
            outros = [j.contribuicao for j in na_mao if j is not vencedor]
            devolvido = max(0, vencedor.contribuicao - max(outros, default=0))
            total = self._pote()
            if devolvido:
                self.emitir("devolucao", nome=vencedor.nome, valor=devolvido)
            self.emitir("ganho", nome=vencedor.nome, valor=total - devolvido, rotulo="pote",
                        showdown=False)
            vencedor.fichas += total
            ganhos[vencedor.nome] = total - devolvido
            return ganhos

        forcas = {}
        for j in vivos:
            forcas[j.nome] = avaliar(j.cartas + self.comunitarias)
            self.emitir("showdown", nome=j.nome, cartas=list(j.cartas), forca=forcas[j.nome],
                        descricao=descrever(forcas[j.nome]), comunitarias=list(self.comunitarias))

        idx_de = {j.nome: k for k, j in enumerate(self.assentos) if j is not None}
        ordem = sorted(na_mao, key=lambda j: (idx_de[j.nome] - self.botao - 1) % MAX_ASSENTOS)
        contrib = {j.nome: j.contribuicao for j in ordem}
        desistiram = [j.nome for j in na_mao if j.desistiu]
        potes = calcular_potes(contrib, desistiram)
        premios, divisoes = distribuir_potes(potes, forcas, [j.nome for j in ordem])

        n_lateral = 0
        disputados = [d for d in divisoes if not d.pote.devolucao]
        for d in divisoes:
            if d.pote.devolucao:
                self.emitir("devolucao", nome=d.vencedores[0], valor=d.pote.valor)
                continue
            if len(disputados) == 1:
                rotulo = "pote"
            elif d is disputados[0]:
                rotulo = "pote principal"
            else:
                n_lateral += 1
                rotulo = f"pote lateral {n_lateral}"
            self.emitir("pote", rotulo=rotulo, valor=d.pote.valor, vencedores=list(d.vencedores),
                        premios=dict(d.premios))
            for nome, v in d.premios.items():
                ganhos[nome] = ganhos.get(nome, 0) + v
                self.emitir("ganho", nome=nome, valor=v, rotulo=rotulo, showdown=True)
        for nome, v in premios.items():
            por_nome[nome].fichas += v
        return ganhos
