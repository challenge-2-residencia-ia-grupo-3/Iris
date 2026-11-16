"""Schema modular e carregador de catálogos de características funcionais (História 4.2.1 - Issue #39).

Implementa a validação estrita dos catálogos JSON/YAML em `rag/catalogs/`, garantindo:
1. Presença obrigatória do `id_caracteristica`, descrição observável em sala de aula (sem exigir laudo),
   mapeamento para `barreira_rag_associada`, diretrizes de andaime para os Níveis 1, 2 e 3 e
   referências bibliográficas válidas (DUA/CAST, MEC, Funções Executivas).
2. Proibição de atributos extras não declarados (`extra = "forbid"`), prevenindo a injeção de
   rótulos clínicos ou CIDs médicos em nível de característica.
3. Extensibilidade automática: novos arquivos `.json` adicionados em `rag/catalogs/` (ex.: TEA, Dislexia)
   são descobertos e validados sem alteração de código-fonte.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from iris.config import CATALOGS_DIR

BARREIRAS_RAG_VALIDAS = frozenset(
    {
        "atencao_sustentada",
        "controle_inibitorio",
        "flexibilidade_cognitiva",
        "iniciacao_tarefa",
        "leitura_texto_longo",
        "memoria_trabalho",
        "organizacao_sequencial",
        "sobrecarga_visual",
        "velocidade_processamento",
    }
)

PRINCIPIOS_DUA_VALIDOS = frozenset(
    {
        "representacao",
        "acao_e_expressao",
        "engajamento",
    }
)

RE_ID_ATOMICO = re.compile(r"^[a-z][a-z0-9_]{5,80}$")


class CatalogValidationError(ValueError):
    """Erro lançado quando um catálogo de características viola o schema oficial ou falta evidência."""


def _check_extra_fields(data: dict[str, Any], allowed: set[str], context: str) -> None:
    extras = set(data.keys()) - allowed
    if extras:
        raise CatalogValidationError(
            f"[{context}] Campos não permitidos detectados (extra='forbid'): {sorted(extras)}"
        )


def _check_non_empty_str(val: Any, field_name: str, context: str, min_len: int = 3) -> str:
    if not isinstance(val, str) or len(val.strip()) < min_len:
        raise CatalogValidationError(
            f"[{context}] Campo obrigatório '{field_name}' deve ser texto com ao menos {min_len} caracteres."
        )
    return val.strip()


def _check_str_list(val: Any, field_name: str, context: str, min_items: int = 1) -> list[str]:
    if not isinstance(val, list) or len(val) < min_items:
        raise CatalogValidationError(
            f"[{context}] Campo '{field_name}' deve ser uma lista com ao menos {min_items} item(ns)."
        )
    cleaned: list[str] = []
    for idx, item in enumerate(val):
        cleaned.append(_check_non_empty_str(item, f"{field_name}[{idx}]", context, min_len=3))
    return cleaned


class BibliographicReference:
    """Referência científica ou normativa que fundamenta a intervenção da característica."""

    ALLOWED_FIELDS = {"doc_id", "citacao_curta", "ponto_verificacao_dua", "tipo_evidencia"}

    def __init__(
        self,
        doc_id: str,
        citacao_curta: str,
        tipo_evidencia: str,
        ponto_verificacao_dua: str | None = None,
    ) -> None:
        self.doc_id = doc_id
        self.citacao_curta = citacao_curta
        self.tipo_evidencia = tipo_evidencia
        self.ponto_verificacao_dua = ponto_verificacao_dua

    @classmethod
    def from_dict(cls, data: dict[str, Any], context: str = "BibliographicReference") -> BibliographicReference:
        if not isinstance(data, dict):
            raise CatalogValidationError(f"[{context}] Referência bibliográfica deve ser um objeto JSON.")
        _check_extra_fields(data, cls.ALLOWED_FIELDS, context)
        doc_id = _check_non_empty_str(data.get("doc_id"), "doc_id", context, min_len=4)
        citacao_curta = _check_non_empty_str(data.get("citacao_curta"), "citacao_curta", context, min_len=10)
        tipo_evidencia = _check_non_empty_str(data.get("tipo_evidencia"), "tipo_evidencia", context, min_len=3)
        ponto = data.get("ponto_verificacao_dua")
        if ponto is not None:
            ponto = _check_non_empty_str(ponto, "ponto_verificacao_dua", context, min_len=3)
        return cls(
            doc_id=doc_id,
            citacao_curta=citacao_curta,
            tipo_evidencia=tipo_evidencia,
            ponto_verificacao_dua=ponto,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "citacao_curta": self.citacao_curta,
            "tipo_evidencia": self.tipo_evidencia,
            "ponto_verificacao_dua": self.ponto_verificacao_dua,
        }


class ScaffoldingLevelGuideline:
    """Diretrizes estruturais para um nível de andaime cognitivo (Nível 1, 2 ou 3)."""

    ALLOWED_FIELDS = {"nivel", "rotulo", "objetivo_andaime", "acoes_permitidas", "restricoes_escopo"}

    def __init__(
        self,
        nivel: int,
        rotulo: str,
        objetivo_andaime: str,
        acoes_permitidas: list[str],
        restricoes_escopo: list[str],
    ) -> None:
        self.nivel = nivel
        self.rotulo = rotulo
        self.objetivo_andaime = objetivo_andaime
        self.acoes_permitidas = acoes_permitidas
        self.restricoes_escopo = restricoes_escopo

    @classmethod
    def from_dict(cls, data: dict[str, Any], expected_level: int, context: str) -> ScaffoldingLevelGuideline:
        if not isinstance(data, dict):
            raise CatalogValidationError(f"[{context}] Diretriz de nível {expected_level} deve ser um objeto JSON.")
        _check_extra_fields(data, cls.ALLOWED_FIELDS, context)
        nivel = data.get("nivel")
        if nivel != expected_level:
            raise CatalogValidationError(
                f"[{context}] Nível esperado {expected_level}, recebido: {nivel!r}."
            )
        rotulo = _check_non_empty_str(data.get("rotulo"), "rotulo", context, min_len=3)
        objetivo = _check_non_empty_str(data.get("objetivo_andaime"), "objetivo_andaime", context, min_len=10)
        acoes = _check_str_list(data.get("acoes_permitidas"), "acoes_permitidas", context, min_items=1)
        restricoes = _check_str_list(data.get("restricoes_escopo"), "restricoes_escopo", context, min_items=1)
        return cls(
            nivel=nivel,
            rotulo=rotulo,
            objetivo_andaime=objetivo,
            acoes_permitidas=acoes,
            restricoes_escopo=restricoes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nivel": self.nivel,
            "rotulo": self.rotulo,
            "objetivo_andaime": self.objetivo_andaime,
            "acoes_permitidas": self.acoes_permitidas,
            "restricoes_escopo": self.restricoes_escopo,
        }


class CharacteristicItem:
    """Característica funcional atômica observável em sala de aula (Pilar 1: Intervenção Cirúrgica)."""

    ALLOWED_FIELDS = {
        "id_caracteristica",
        "nome",
        "descricao_observavel",
        "exemplos_manifestacao_sala",
        "barreira_rag_associada",
        "principio_dua_primario",
        "palavras_chave_busca",
        "diretrizes_andaime",
        "referencias_bibliograficas",
    }

    def __init__(
        self,
        id_caracteristica: str,
        nome: str,
        descricao_observavel: str,
        exemplos_manifestacao_sala: list[str],
        barreira_rag_associada: str,
        principio_dua_primario: str,
        palavras_chave_busca: list[str],
        diretrizes_andaime: dict[str, ScaffoldingLevelGuideline],
        referencias_bibliograficas: list[BibliographicReference],
    ) -> None:
        self.id_caracteristica = id_caracteristica
        self.nome = nome
        self.descricao_observavel = descricao_observavel
        self.exemplos_manifestacao_sala = exemplos_manifestacao_sala
        self.barreira_rag_associada = barreira_rag_associada
        self.principio_dua_primario = principio_dua_primario
        self.palavras_chave_busca = palavras_chave_busca
        self.diretrizes_andaime = diretrizes_andaime
        self.referencias_bibliograficas = referencias_bibliograficas

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacteristicItem:
        if not isinstance(data, dict):
            raise CatalogValidationError("Item de característica deve ser um objeto JSON.")
        cid = _check_non_empty_str(data.get("id_caracteristica"), "id_caracteristica", "CharacteristicItem", min_len=6)
        ctx = f"CharacteristicItem({cid})"
        _check_extra_fields(data, cls.ALLOWED_FIELDS, ctx)

        if not RE_ID_ATOMICO.match(cid):
            raise CatalogValidationError(
                f"[{ctx}] 'id_caracteristica' deve estar em snake_case minúsculo (recebido: {cid!r})."
            )

        nome = _check_non_empty_str(data.get("nome"), "nome", ctx, min_len=5)
        descricao = _check_non_empty_str(data.get("descricao_observavel"), "descricao_observavel", ctx, min_len=20)
        exemplos = _check_str_list(data.get("exemplos_manifestacao_sala"), "exemplos_manifestacao_sala", ctx, min_items=1)

        barreira = _check_non_empty_str(data.get("barreira_rag_associada"), "barreira_rag_associada", ctx)
        if barreira not in BARREIRAS_RAG_VALIDAS:
            raise CatalogValidationError(
                f"[{ctx}] 'barreira_rag_associada' inválida ({barreira!r}). "
                f"Valores permitidos: {sorted(BARREIRAS_RAG_VALIDAS)}"
            )

        principio = _check_non_empty_str(data.get("principio_dua_primario"), "principio_dua_primario", ctx)
        if principio not in PRINCIPIOS_DUA_VALIDOS:
            raise CatalogValidationError(
                f"[{ctx}] 'principio_dua_primario' inválido ({principio!r}). "
                f"Valores permitidos: {sorted(PRINCIPIOS_DUA_VALIDOS)}"
            )

        palavras_chave = _check_str_list(data.get("palavras_chave_busca"), "palavras_chave_busca", ctx, min_items=2)

        raw_andaimes = data.get("diretrizes_andaime")
        if not isinstance(raw_andaimes, dict):
            raise CatalogValidationError(f"[{ctx}] 'diretrizes_andaime' deve ser um objeto mapeando 'nivel_1', 'nivel_2' e 'nivel_3'.")
        expected_keys = {"nivel_1": 1, "nivel_2": 2, "nivel_3": 3}
        _check_extra_fields(raw_andaimes, set(expected_keys.keys()), f"{ctx}.diretrizes_andaime")
        andaimes: dict[str, ScaffoldingLevelGuideline] = {}
        for k, lvl in expected_keys.items():
            if k not in raw_andaimes:
                raise CatalogValidationError(f"[{ctx}] Diretriz obrigatória '{k}' ausente em 'diretrizes_andaime'.")
            andaimes[k] = ScaffoldingLevelGuideline.from_dict(raw_andaimes[k], lvl, f"{ctx}.{k}")

        raw_refs = data.get("referencias_bibliograficas")
        if not isinstance(raw_refs, list) or len(raw_refs) < 1:
            raise CatalogValidationError(
                f"[{ctx}] Catálogo rejeitado: toda característica deve possuir ao menos 1 referência bibliográfica válida."
            )
        refs = [
            BibliographicReference.from_dict(r, f"{ctx}.referencias_bibliograficas[{i}]")
            for i, r in enumerate(raw_refs)
        ]

        return cls(
            id_caracteristica=cid,
            nome=nome,
            descricao_observavel=descricao,
            exemplos_manifestacao_sala=exemplos,
            barreira_rag_associada=barreira,
            principio_dua_primario=principio,
            palavras_chave_busca=palavras_chave,
            diretrizes_andaime=andaimes,
            referencias_bibliograficas=refs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_caracteristica": self.id_caracteristica,
            "nome": self.nome,
            "descricao_observavel": self.descricao_observavel,
            "exemplos_manifestacao_sala": self.exemplos_manifestacao_sala,
            "barreira_rag_associada": self.barreira_rag_associada,
            "principio_dua_primario": self.principio_dua_primario,
            "palavras_chave_busca": self.palavras_chave_busca,
            "diretrizes_andaime": {k: v.to_dict() for k, v in self.diretrizes_andaime.items()},
            "referencias_bibliograficas": [r.to_dict() for r in self.referencias_bibliograficas],
        }


class CharacteristicCatalog:
    """Catálogo modular de características funcionais (ex.: TDAH, TEA, Dislexia)."""

    ALLOWED_FIELDS = {
        "id_catalogo",
        "versao_schema",
        "perfil_referencia",
        "titulo",
        "descricao",
        "aviso_etico_lgpd",
        "caracteristicas",
    }

    def __init__(
        self,
        id_catalogo: str,
        versao_schema: str,
        perfil_referencia: str,
        titulo: str,
        descricao: str,
        aviso_etico_lgpd: str,
        caracteristicas: list[CharacteristicItem],
    ) -> None:
        self.id_catalogo = id_catalogo
        self.versao_schema = versao_schema
        self.perfil_referencia = perfil_referencia
        self.titulo = titulo
        self.descricao = descricao
        self.aviso_etico_lgpd = aviso_etico_lgpd
        self.caracteristicas = caracteristicas
        self._por_id = {c.id_caracteristica: c for c in caracteristicas}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacteristicCatalog:
        if not isinstance(data, dict):
            raise CatalogValidationError("O catálogo raiz deve ser um objeto JSON.")
        id_cat = _check_non_empty_str(data.get("id_catalogo"), "id_catalogo", "CharacteristicCatalog", min_len=3)
        ctx = f"CharacteristicCatalog({id_cat})"
        _check_extra_fields(data, cls.ALLOWED_FIELDS, ctx)

        versao = _check_non_empty_str(data.get("versao_schema"), "versao_schema", ctx, min_len=3)
        perfil = _check_non_empty_str(data.get("perfil_referencia"), "perfil_referencia", ctx, min_len=2)
        titulo = _check_non_empty_str(data.get("titulo"), "titulo", ctx, min_len=5)
        descricao = _check_non_empty_str(data.get("descricao"), "descricao", ctx, min_len=15)
        aviso = _check_non_empty_str(data.get("aviso_etico_lgpd"), "aviso_etico_lgpd", ctx, min_len=15)

        raw_chars = data.get("caracteristicas")
        if not isinstance(raw_chars, list) or len(raw_chars) < 1:
            raise CatalogValidationError(f"[{ctx}] O catálogo deve conter ao menos 1 característica funcional.")

        itens: list[CharacteristicItem] = []
        vistos: set[str] = set()
        for raw in raw_chars:
            item = CharacteristicItem.from_dict(raw)
            if item.id_caracteristica in vistos:
                raise CatalogValidationError(
                    f"[{ctx}] 'id_caracteristica' duplicado no catálogo: {item.id_caracteristica!r}"
                )
            vistos.add(item.id_caracteristica)
            itens.append(item)

        return cls(
            id_catalogo=id_cat,
            versao_schema=versao,
            perfil_referencia=perfil,
            titulo=titulo,
            descricao=descricao,
            aviso_etico_lgpd=aviso,
            caracteristicas=itens,
        )

    def get_characteristic(self, id_caracteristica: str) -> CharacteristicItem:
        if id_caracteristica not in self._por_id:
            raise KeyError(
                f"Característica {id_caracteristica!r} não encontrada no catálogo {self.id_catalogo!r}."
            )
        return self._por_id[id_caracteristica]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_catalogo": self.id_catalogo,
            "versao_schema": self.versao_schema,
            "perfil_referencia": self.perfil_referencia,
            "titulo": self.titulo,
            "descricao": self.descricao,
            "aviso_etico_lgpd": self.aviso_etico_lgpd,
            "caracteristicas": [c.to_dict() for c in self.caracteristicas],
        }


def load_catalog_file(path: Path) -> CharacteristicCatalog:
    """Carrega e valida estritamente um arquivo de catálogo `.json`."""
    raw_text = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw_text)
    return CharacteristicCatalog.from_dict(data)


def load_all_catalogs(directory: Path = CATALOGS_DIR) -> dict[str, CharacteristicCatalog]:
    """Descobre e valida todos os catálogos `.json` no diretório `rag/catalogs/`."""
    directory = Path(directory)
    if not directory.exists():
        return {}
    catalogs: dict[str, CharacteristicCatalog] = {}
    for file_path in sorted(directory.glob("*.json")):
        cat = load_catalog_file(file_path)
        if cat.id_catalogo in catalogs:
            raise CatalogValidationError(f"ID de catálogo duplicado entre arquivos: {cat.id_catalogo!r}")
        catalogs[cat.id_catalogo] = cat
    return catalogs


def load_official_tdah_catalog(directory: Path = CATALOGS_DIR) -> CharacteristicCatalog:
    """Carrega o catálogo oficial de características funcionais atômicas do TDAH."""
    tdah_path = Path(directory) / "tdah_caracteristicas_funcionais.json"
    if tdah_path.exists():
        return load_catalog_file(tdah_path)
    catalogs = load_all_catalogs(directory)
    if not catalogs:
        raise CatalogValidationError(f"Nenhum catálogo funcional encontrado em {directory}.")
    return next(iter(catalogs.values()))


def get_characteristic_by_id(
    id_caracteristica: str, directory: Path = CATALOGS_DIR
) -> CharacteristicItem:
    """Busca uma característica atômica pelo seu identificador em todos os catálogos carregados."""
    for cat in load_all_catalogs(directory).values():
        if id_caracteristica in cat._por_id:
            return cat.get_characteristic(id_caracteristica)
    raise KeyError(f"Característica funcional {id_caracteristica!r} não encontrada em nenhum catálogo ativo.")


class CharacteristicSelectionError(ValueError):
    """Erro de validação na seleção cirúrgica de características funcionais (História 1.2.1 - Issue #8)."""

    def __init__(self, message: str, code: str, field: str = "selected_ids") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field

    def to_dict(self) -> dict[str, str]:
        return {"detail": self.message, "code": self.code, "field": self.field}


class SurgicalCharacteristicSelection:
    """Vetor cirúrgico de características ativadas e bloqueadas para a sessão (RF-04 / RF-05)."""

    def __init__(
        self,
        status: str,
        message: str,
        id_catalogo: str,
        total_catalog_characteristics: int,
        selected_ids: list[str],
        blocked_ids: list[str],
        active_characteristics: list[dict[str, Any]],
        scope_isolation_rule: str,
        engagement_metadata: dict[str, Any] | None = None,
        motivational_context: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.id_catalogo = id_catalogo
        self.total_catalog_characteristics = total_catalog_characteristics
        self.selected_ids = selected_ids
        self.blocked_ids = blocked_ids
        self.selected_count = len(selected_ids)
        self.blocked_count = len(blocked_ids)
        self.active_characteristics = active_characteristics
        self.scope_isolation_rule = scope_isolation_rule
        self.engagement_metadata = engagement_metadata
        self.motivational_context = motivational_context

    def model_dump(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "message": self.message,
            "id_catalogo": self.id_catalogo,
            "total_catalog_characteristics": self.total_catalog_characteristics,
            "selected_count": self.selected_count,
            "blocked_count": self.blocked_count,
            "selected_ids": list(self.selected_ids),
            "blocked_ids": list(self.blocked_ids),
            "active_characteristics": list(self.active_characteristics),
            "scope_isolation_rule": self.scope_isolation_rule,
        }
        if self.engagement_metadata is not None:
            payload["engagement_metadata"] = self.engagement_metadata
        if self.motivational_context is not None:
            payload["motivational_context"] = self.motivational_context
        return payload

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


def validate_surgical_characteristic_selection(
    selected_ids: Any,
    catalog: CharacteristicCatalog | None = None,
    directory: Path = CATALOGS_DIR,
) -> SurgicalCharacteristicSelection:
    """Valida e constrói o vetor cirúrgico de características funcionais (RF-04 / Issue #8).

    Regras de negócio:
    1. Pelo menos 1 característica funcional atômica deve ser selecionada (impede avanço se vazia).
    2. Todas as características selecionadas devem existir no catálogo oficial validado.
    3. As características não assinaladas são explicitamente registradas em `blocked_ids` para
       garantir o isolamento estrito de escopo (Pilar 1: Intervenção Cirúrgica).
    """
    if not isinstance(selected_ids, list):
        raise CharacteristicSelectionError(
            message="O campo 'selected_ids' deve ser uma lista de identificadores de características funcionais.",
            code="INVALID_SELECTION_TYPE",
            field="selected_ids",
        )

    cleaned_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in selected_ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise CharacteristicSelectionError(
                message="Todos os identificadores em 'selected_ids' devem ser textos não vazios.",
                code="INVALID_CHARACTERISTIC_ID",
                field="selected_ids",
            )
        cid = raw_id.strip()
        if cid not in seen:
            seen.add(cid)
            cleaned_ids.append(cid)

    if len(cleaned_ids) == 0:
        raise CharacteristicSelectionError(
            message=(
                "Selecione pelo menos uma característica funcional observada em sala de aula "
                "para definir o escopo permitido de adaptação antes de avançar."
            ),
            code="EMPTY_CHARACTERISTIC_SELECTION",
            field="selected_ids",
        )

    active_catalog = catalog or load_official_tdah_catalog(directory=directory)
    unknown_ids = [cid for cid in cleaned_ids if cid not in active_catalog._por_id]
    if unknown_ids:
        raise CharacteristicSelectionError(
            message=(
                f"Característica(s) funcional(is) não reconhecida(s) no catálogo '{active_catalog.id_catalogo}': "
                f"{', '.join(unknown_ids)}."
            ),
            code="UNKNOWN_CHARACTERISTIC_ID",
            field="selected_ids",
        )

    active_items = [active_catalog.get_characteristic(cid).to_dict() for cid in cleaned_ids]
    blocked_ids = [
        c.id_caracteristica
        for c in active_catalog.caracteristicas
        if c.id_caracteristica not in seen
    ]

    return SurgicalCharacteristicSelection(
        status="success",
        message=(
            f"Escopo cirúrgico registrado: {len(cleaned_ids)} característica(s) ativada(s) para adaptação "
            f"e {len(blocked_ids)} característica(s) bloqueada(s) para preservar a autonomia do estudante."
        ),
        id_catalogo=active_catalog.id_catalogo,
        total_catalog_characteristics=len(active_catalog.caracteristicas),
        selected_ids=cleaned_ids,
        blocked_ids=blocked_ids,
        active_characteristics=active_items,
        scope_isolation_rule=(
            "O pipeline de adaptação atuará exclusivamente sobre as características em 'selected_ids'. "
            "Todas as dimensões listadas em 'blocked_ids' permanecem bloqueadas para intervenção, "
            "preservando 100% da estrutura e autonomia original."
        ),
    )

