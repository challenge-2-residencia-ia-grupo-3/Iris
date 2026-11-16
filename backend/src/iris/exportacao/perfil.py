"""Serializadores do Perfil Pedagógico Portátil para download local (`.json` e `.pdf`).

Regras (RF-15, RNF-01):
- O servidor NÃO guarda o perfil: cada chamada recebe o perfil, valida, converte e devolve os bytes.
  Não há arquivo temporário, cache, variável global nem banco de dados neste módulo.
- Todo perfil passa por `validar_perfil` (schema oficial + bloqueio de laudo/CID/diagnóstico/medicação, #28)
  antes de virar arquivo. Um perfil inválido nunca gera `.json` nem `.pdf`.
- O PDF é montado em memória com PyMuPDF (já dependência do projeto), com todo texto escapado.
- O texto livre (anotações, observações, estratégias) passa por `sanitize_pii` antes de virar arquivo: CPF,
  telefone, e-mail e matrícula saem como marcadores. Nome de pessoa em texto corrido não é detectado.
"""
from __future__ import annotations

import html
import io
import json
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Mapping

from iris.schemas.catalog import load_all_catalogs
from iris.schemas.portable_profile import PerfilPedagogico, validar_perfil
from iris.security.pii_scrubber import sanitize_pii

FORMATOS = ("json", "pdf")
MEDIA_TYPES = {"json": "application/json", "pdf": "application/pdf"}


class FormatoInvalidoError(ValueError):
    def __init__(self, formato: object) -> None:
        super().__init__(f"Formato de exportação não suportado: use um de {', '.join(FORMATOS)}.")
        self.formato = formato

    def to_dict(self) -> dict[str, str]:
        return {"detail": str(self), "code": "UNSUPPORTED_EXPORT_FORMAT", "field": "formato"}


@dataclass(frozen=True)
class ArquivoExportado:
    nome: str
    media_type: str
    conteudo: bytes


def perfil_para_json_bytes(perfil: PerfilPedagogico) -> bytes:
    return json.dumps(perfil.para_json(), ensure_ascii=False, indent=2).encode("utf-8")


def _limpo(texto: str | None) -> str | None:
    return sanitize_pii(texto)[0] if texto else texto


def sem_dado_pessoal(perfil: PerfilPedagogico) -> PerfilPedagogico:
    """Cópia do perfil com o texto livre sanitizado (RNF-01). Os campos de formato fechado não mudam.

    Usa `model_copy`, sem revalidar: um marcador pode ser mais longo que o trecho que substitui.
    """
    return perfil.model_copy(update={
        "barreiras_observadas": [
            b.model_copy(update={"observacao": _limpo(b.observacao)}) for b in perfil.barreiras_observadas
        ],
        "historico_estrategias": [
            r.model_copy(update={"estrategia": _limpo(r.estrategia), "observacao": _limpo(r.observacao)})
            for r in perfil.historico_estrategias
        ],
        "anotacoes_pedagogicas": [_limpo(a) for a in perfil.anotacoes_pedagogicas],
    })


def _catalogo_por_id() -> dict[str, Any]:
    """Itens do catálogo oficial (nome legível e descrição). Se o catálogo não carregar, o PDF usa o próprio ID."""
    try:
        return {c.id_caracteristica: c for cat in load_all_catalogs().values() for c in cat.caracteristicas}
    except Exception:  # noqa: BLE001 - o relatório não pode falhar por causa do catálogo
        return {}


_CSS = """
body { font-family: sans-serif; font-size: 10.5pt; color: #0D0221; }
h1 { font-size: 18pt; margin-bottom: 2pt; }
h2 { font-size: 12.5pt; margin-top: 14pt; margin-bottom: 3pt; color: #335C67; }
p { margin: 2pt 0; }
.meta { color: #444444; font-size: 9.5pt; }
.cod { font-family: monospace; font-weight: bold; }
.item { margin: 5pt 0; }
.nota { font-size: 8.5pt; color: #555555; margin-top: 16pt; }
"""


def _e(valor: object) -> str:
    return html.escape(str(valor), quote=True)


def _html_relatorio(perfil: PerfilPedagogico) -> str:
    catalogo = _catalogo_por_id()
    criado = perfil.criado_em.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    partes = [
        "<h1>Perfil Pedagógico Portátil</h1>",
        '<p class="meta">Plataforma Íris — relatório síntese para anexar ao PDI</p>',
        f'<p>Código anônimo: <span class="cod">{_e(perfil.codigo_anonimo)}</span></p>',
        f'<p class="meta">Gerado em {_e(criado)} • versão do formato {_e(perfil.versao_schema)}</p>',
        "<h2>Características funcionais observadas</h2>",
    ]
    if perfil.caracteristicas_selecionadas:
        for id_c in perfil.caracteristicas_selecionadas:
            item = catalogo.get(id_c)
            if item is not None:
                partes.append(f'<div class="item"><p><b>{_e(item.nome)}</b></p><p>{_e(item.descricao_observavel)}</p></div>')
            else:
                partes.append(f'<div class="item"><p><b>{_e(id_c)}</b></p></div>')
    else:
        partes.append("<p>Nenhuma característica selecionada.</p>")

    if perfil.barreiras_observadas:
        partes.append("<h2>Barreiras observadas</h2>")
        for b in perfil.barreiras_observadas:
            item = catalogo.get(b.id_caracteristica)
            rotulo = item.nome if item is not None else b.id_caracteristica
            obs = f" — {_e(b.observacao)}" if b.observacao else ""
            partes.append(f'<div class="item"><p><b>{_e(rotulo)}</b>{obs}</p></div>')
    if perfil.historico_estrategias:
        partes.append("<h2>Estratégias já utilizadas</h2>")
        for r in perfil.historico_estrategias:
            obs = f" — {_e(r.observacao)}" if r.observacao else ""
            partes.append(f'<div class="item"><p><b>{_e(r.estrategia)}</b> ({_e(r.resultado)}){obs}</p></div>')
    if perfil.anotacoes_pedagogicas:
        partes.append("<h2>Anotações pedagógicas</h2>")
        partes += [f"<p>{_e(a)}</p>" for a in perfil.anotacoes_pedagogicas]

    partes.append(
        '<p class="nota">Este documento foi gerado sem armazenamento no servidor. Laudo, CID, diagnóstico e '
        "medicação são recusados na validação; documentos e contatos em texto livre são trocados por marcadores. "
        "Nome de pessoa não é detectado automaticamente: revise antes de compartilhar. "
        "A guarda do arquivo é de responsabilidade do docente.</p>"
    )
    return "".join(partes)


def perfil_para_pdf_bytes(perfil: PerfilPedagogico) -> bytes:
    try:
        import pymupdf
    except ImportError:  # versões antigas expõem apenas `fitz`
        import fitz as pymupdf  # type: ignore[no-redef]

    saida = io.BytesIO()
    story = pymupdf.Story(html=_html_relatorio(perfil), user_css=_CSS)
    writer = pymupdf.DocumentWriter(saida)
    pagina = pymupdf.paper_rect("a4")
    area = pagina + (48, 48, -48, -48)
    mais = 1
    while mais:
        dev = writer.begin_page(pagina)
        mais, _ = story.place(area)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return saida.getvalue()


def exportar_perfil(dados: Mapping[str, Any] | str | bytes, formato: str) -> ArquivoExportado:
    """Valida o perfil e devolve o arquivo em memória. Levanta `PerfilInvalidoError` ou `FormatoInvalidoError`."""
    if formato not in FORMATOS:
        raise FormatoInvalidoError(formato)
    perfil = sem_dado_pessoal(validar_perfil(dados))
    conteudo = perfil_para_json_bytes(perfil) if formato == "json" else perfil_para_pdf_bytes(perfil)
    return ArquivoExportado(
        nome=f"perfil-{perfil.codigo_anonimo}.{formato}",
        media_type=MEDIA_TYPES[formato],
        conteudo=conteudo,
    )
