"""Revisão docente da atividade adaptada, em memória (História 2.2.2, RF-13 e RNF-09).

O professor é a autoridade pedagógica: edita qualquer palavra da versão sugerida pela IA, aprova
questão por questão e, no fim, homologa. Só depois da homologação o arquivo final pode ser gerado.

Regras de Human-in-the-Loop, todas aplicadas AQUI (o front só reflete):
- uma questão só vale como aprovada se o texto aprovado é o que está na sessão: editar uma questão
  aprovada tira a aprovação dela E revoga a homologação;
- a homologação exige TODAS as questões aprovadas;
- a exportação é recusada (EXPORT_BLOCKED) sem homologação. Não há "modo de teste" nem parâmetro de bypass.

Zero-retenção (RNF-01/02): as sessões vivem só na memória do processo, expiram por inatividade (TTL),
há teto de sessões simultâneas, e nada vai a disco, banco ou rede. O corpo digitado pelo professor não é
alterado; o aviso de dado pessoal/termo clínico continua em `exportacao.material.verificar_material`.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from iris.exportacao.material import (
    ArquivoMaterial,
    MAX_TEXTO,
    MAX_TITULO,
    exportar_material,
    verificar_material,
)

TTL_SEGUNDOS = 2 * 60 * 60
MAX_SESSOES = 200
MAX_QUESTOES = 100
MAX_ENUNCIADO = 5_000
SEPARADOR_QUESTOES = "\n\n"


class SessaoError(ValueError):
    """Erro de regra da sessão. `status` orienta o HTTP: 404, 409 ou 422."""

    def __init__(self, mensagem: str, code: str, field: str = "", status: int = 422) -> None:
        super().__init__(mensagem)
        self.code, self.field, self.status = code, field, status

    def to_dict(self) -> dict[str, str]:
        return {"status": "error", "code": self.code, "field": self.field, "detail": str(self)}


@dataclass
class Questao:
    id: str
    original: str
    adaptado: str
    aprovada: bool = False
    editada: bool = False

    def publico(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original": self.original,
            "adaptado": self.adaptado,
            "aprovada": self.aprovada,
            "editada": self.editada,
        }


@dataclass
class Sessao:
    id: str
    titulo: str
    questoes: list[Questao]
    homologada: bool = False
    revisao: int = 0
    ultimo_acesso: float = field(default_factory=time.monotonic)

    @property
    def todas_aprovadas(self) -> bool:
        return bool(self.questoes) and all(q.aprovada for q in self.questoes)

    def texto_final(self) -> str:
        return SEPARADOR_QUESTOES.join(q.adaptado.strip() for q in self.questoes)

    def publico(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "revisao": self.revisao,
            "homologada": self.homologada,
            "pode_exportar": self.homologada,
            "pode_homologar": self.todas_aprovadas,
            "questoes": [q.publico() for q in self.questoes],
            "versao_final": self.texto_final(),
        }


def _texto(valor: Any, campo: str, maximo: int, *, obrigatorio: bool = True) -> str:
    if not isinstance(valor, str):
        raise SessaoError(f"O campo '{campo}' deve ser um texto.", "INVALID_FIELD", campo)
    if obrigatorio and not valor.strip():
        raise SessaoError(f"O campo '{campo}' não pode ficar vazio.", "EMPTY_FIELD", campo)
    if len(valor) > maximo:
        raise SessaoError(f"O campo '{campo}' passa de {maximo} caracteres.", "FIELD_TOO_LONG", campo)
    return valor


def _objeto(dados: Any, aceitos: frozenset[str], nome: str) -> Mapping[str, Any]:
    if not isinstance(dados, Mapping):
        raise SessaoError(f"{nome} deve ser um objeto JSON.", "INVALID_BODY", "body")
    extras = sorted(str(k) for k in dados if k not in aceitos)
    if extras:
        raise SessaoError(
            f"Campos não aceitos em {nome}: {', '.join(extras)}.", "UNKNOWN_FIELD", extras[0]
        )
    return dados


class RepositorioSessoes:
    """Armazém em memória, seguro para threads, com TTL e teto de sessões."""

    def __init__(self, ttl: float = TTL_SEGUNDOS, maximo: int = MAX_SESSOES, relogio: Callable[[], float] = time.monotonic) -> None:
        self._sessoes: dict[str, Sessao] = {}
        self._trava = threading.RLock()
        self._ttl, self._maximo, self._relogio = ttl, maximo, relogio

    # -- infra ---------------------------------------------------------------------------------
    def _expirar(self) -> None:
        agora = self._relogio()
        for sid in [s for s, v in self._sessoes.items() if agora - v.ultimo_acesso > self._ttl]:
            del self._sessoes[sid]

    def _obter(self, sid: str) -> Sessao:
        self._expirar()
        sessao = self._sessoes.get(sid) if isinstance(sid, str) else None
        if sessao is None:
            raise SessaoError("Sessão não encontrada ou expirada.", "SESSION_NOT_FOUND", "id", status=404)
        sessao.ultimo_acesso = self._relogio()
        return sessao

    def __len__(self) -> int:
        with self._trava:
            self._expirar()
            return len(self._sessoes)

    # -- operações -----------------------------------------------------------------------------
    def criar(self, dados: Any) -> dict[str, Any]:
        corpo = _objeto(dados, frozenset({"titulo", "questoes"}), "a sessão")
        titulo = corpo.get("titulo") or ""
        _texto(titulo, "titulo", MAX_TITULO, obrigatorio=False)
        brutas = corpo.get("questoes")
        if not isinstance(brutas, list) or not brutas:
            raise SessaoError("Envie ao menos uma questão.", "NO_QUESTIONS", "questoes")
        if len(brutas) > MAX_QUESTOES:
            raise SessaoError(f"No máximo {MAX_QUESTOES} questões por sessão.", "TOO_MANY_QUESTIONS", "questoes")
        questoes: list[Questao] = []
        vistos: set[str] = set()
        for i, bruta in enumerate(brutas, start=1):
            q = _objeto(bruta, frozenset({"id", "original", "adaptado"}), f"a questão {i}")
            qid = _texto(q.get("id", f"q{i}"), "id", 64)
            if qid in vistos:
                raise SessaoError(f"Id de questão repetido: {qid}.", "DUPLICATE_QUESTION", "id")
            vistos.add(qid)
            original = _texto(q.get("original", ""), "original", MAX_ENUNCIADO, obrigatorio=False)
            adaptado = _texto(q.get("adaptado"), "adaptado", MAX_ENUNCIADO)
            questoes.append(Questao(id=qid, original=original, adaptado=adaptado))
        if sum(len(q.adaptado) for q in questoes) > MAX_TEXTO:
            raise SessaoError("O material passa do tamanho máximo.", "FIELD_TOO_LONG", "questoes")
        with self._trava:
            self._expirar()
            if len(self._sessoes) >= self._maximo:
                raise SessaoError("Muitas sessões abertas. Tente novamente em instantes.", "TOO_MANY_SESSIONS", "", status=409)
            sid = secrets.token_urlsafe(16)
            sessao = Sessao(id=sid, titulo=titulo.strip(), questoes=questoes, ultimo_acesso=self._relogio())
            self._sessoes[sid] = sessao
            return sessao.publico()

    def ler(self, sid: str) -> dict[str, Any]:
        with self._trava:
            return self._obter(sid).publico()

    def revisar(self, sid: str, dados: Any) -> dict[str, Any]:
        """PUT /sessions/{id}/review: aplica edições, aprovações e a homologação, tudo ou nada."""
        corpo = _objeto(dados, frozenset({"questoes", "homologar"}), "a revisão")
        itens = corpo.get("questoes", [])
        homologar = corpo.get("homologar")
        if not isinstance(itens, list):
            raise SessaoError("O campo 'questoes' deve ser uma lista.", "INVALID_FIELD", "questoes")
        if homologar is not None and not isinstance(homologar, bool):
            raise SessaoError("O campo 'homologar' deve ser verdadeiro ou falso.", "INVALID_FIELD", "homologar")
        with self._trava:
            sessao = self._obter(sid)
            por_id = {q.id: q for q in sessao.questoes}
            # valida tudo antes de mexer: ou aplica tudo, ou nada
            plano: list[tuple[Questao, str | None, bool | None]] = []
            for i, item in enumerate(itens, start=1):
                it = _objeto(item, frozenset({"id", "adaptado", "aprovada"}), f"o item {i}")
                qid = it.get("id")
                if qid not in por_id:
                    raise SessaoError(f"Questão inexistente na sessão: {qid}.", "UNKNOWN_QUESTION", "id")
                novo = it.get("adaptado")
                if novo is not None:
                    novo = _texto(novo, "adaptado", MAX_ENUNCIADO)
                ap = it.get("aprovada")
                if ap is not None and not isinstance(ap, bool):
                    raise SessaoError("O campo 'aprovada' deve ser verdadeiro ou falso.", "INVALID_FIELD", "aprovada")
                plano.append((por_id[qid], novo, ap))

            mudou = False
            for q, novo, ap in plano:
                alterou_texto = novo is not None and novo != q.adaptado
                if alterou_texto:
                    q.adaptado, q.editada, q.aprovada = novo, True, False  # editar invalida a aprovação
                    mudou = True
                if ap is not None and ap != q.aprovada:  # editar+aprovar na mesma chamada aprova a versão nova
                    q.aprovada = ap
                    mudou = True
            total = sum(len(q.adaptado) for q in sessao.questoes)
            if total > MAX_TEXTO:
                raise SessaoError("O material passa do tamanho máximo.", "FIELD_TOO_LONG", "questoes")

            if mudou and sessao.homologada:
                sessao.homologada = False  # qualquer mudança depois de homologar exige nova confirmação
            if homologar is True:
                if not sessao.todas_aprovadas:
                    raise SessaoError(
                        "Aprove todas as questões antes de homologar a atividade.",
                        "NOT_ALL_APPROVED",
                        "homologar",
                        status=409,
                    )
                sessao.homologada = True
            elif homologar is False:
                sessao.homologada = False
            if mudou or homologar is not None:
                sessao.revisao += 1
            return sessao.publico()

    def exportar(self, sid: str, formato: str) -> ArquivoMaterial:
        with self._trava:
            sessao = self._obter(sid)
            if not (sessao.homologada and sessao.todas_aprovadas):
                raise SessaoError(
                    "A exportação só é liberada depois que o professor revisar e homologar a atividade.",
                    "EXPORT_BLOCKED",
                    "homologar",
                    status=409,
                )
            titulo, texto = sessao.titulo, sessao.texto_final()
        # fora da trava: gerar o arquivo pode demorar e não mexe na sessão
        from iris.exportacao.material import ExportacaoMaterialError

        try:
            return exportar_material({"titulo": titulo, "texto": texto}, formato)
        except ExportacaoMaterialError as err:
            raise SessaoError(str(err), err.code, err.field) from err

    def verificar(self, sid: str) -> dict[str, Any]:
        with self._trava:
            sessao = self._obter(sid)
            titulo, texto = sessao.titulo, sessao.texto_final()
        from iris.exportacao.material import ExportacaoMaterialError

        try:
            return verificar_material({"titulo": titulo, "texto": texto})
        except ExportacaoMaterialError as err:
            raise SessaoError(str(err), err.code, err.field) from err

    def descartar(self, sid: str) -> None:
        with self._trava:
            self._obter(sid)
            del self._sessoes[sid]


REPOSITORIO = RepositorioSessoes()
