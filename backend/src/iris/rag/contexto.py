"""Mapeador de contexto do Agente Estrategista (Issue #16, tarefa 3).

Recebe o resultado de ``buscar_por_caracteristica_atomica`` para cada característica ativada pelo
professor e devolve o bloco de contexto que entra no prompt do agente: a diretriz de andaime de cada
característica, os invariantes curriculares e os trechos da base, numerados ``[T1]..[Tn]``, cada um
com a referência bibliográfica que permite citá-lo.

É uma função pura: não busca, não chama LLM e não depende de banco. O agente chama a busca, passa
o resultado por aqui e envia o texto ao modelo; depois confere a diretiva com
``conferir_citacoes``.

Regras que o mapeador garante:
  * um trecho recuperado para duas características aparece uma vez, com as duas indicadas;
  * a característica sem nenhum trecho recuperado interrompe a montagem (``ValueError``): sem
    evidência não há diretiva;
  * o aviso de uso de um trecho (``nao_usar_para``) acompanha o trecho no prompt.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

REGRAS_DE_CITACAO = (
    "REGRAS DE CITAÇÃO:\n"
    "1. Use somente os trechos em TRECHOS; não use conhecimento próprio.\n"
    "2. Toda intervenção proposta termina com a citação do trecho que a sustenta, no formato [T1].\n"
    "3. Use um trecho apenas para a característica indicada nele.\n"
    "4. Respeite o AVISO DE USO quando houver.\n"
    "5. Não proponha intervenção para característica que não esteja em CARACTERÍSTICAS ATIVADAS."
)


def _referencia(t: dict[str, Any]) -> str:
    pagina = f", p. {t['pagina']}" if t.get("pagina") else ""
    return f"{t['titulo']}{pagina}. Disponível em: {t['url']}"


def montar_contexto_estrategista(
    buscas: Sequence[dict[str, Any]],
    invariantes: Sequence[str] = (),
) -> dict[str, Any]:
    """Monta o contexto do prompt a partir das buscas por característica.

    Devolve ``{"contexto": str, "fontes": list[dict], "caracteristicas": list[str]}``. Cada fonte
    traz o rótulo (``T1``), o identificador do trecho, o documento, a página, o endereço, a
    referência pronta e as características a que o trecho serve.
    """
    if not buscas:
        raise ValueError("Nenhuma característica ativada: não há contexto a montar.")

    fontes: list[dict[str, Any]] = []
    por_trecho: dict[str, dict[str, Any]] = {}
    linhas_caracteristicas: list[str] = []
    for busca in buscas:
        id_carac = busca["id_caracteristica"]
        if not busca.get("trechos_rag"):
            raise ValueError(f"Característica {id_carac!r} sem trecho recuperado: sem evidência não há diretiva.")
        diretriz = busca.get("diretriz_andaime") or {}
        linhas_caracteristicas.append(
            f"- {id_carac} ({busca['nome_caracteristica']}), nível {busca['nivel_selecionado']}"
            f"\n  Objetivo do andaime: {diretriz.get('objetivo_andaime', '')}"
            f"\n  Ações permitidas: {'; '.join(diretriz.get('acoes_permitidas', []))}"
            f"\n  Restrições de escopo: {'; '.join(diretriz.get('restricoes_escopo', []))}"
        )
        for t in busca["trechos_rag"]:
            fonte = por_trecho.get(t["chunk_id"])
            if fonte is None:
                nota = (t.get("nota_uso") or "").strip()
                nao_usar = t.get("nao_usar_para") or []
                aviso_de_uso = nota or (
                    f"Não usar para: {', '.join(nao_usar)}." if nao_usar else None
                )
                fonte = {
                    "rotulo": f"T{len(fontes) + 1}",
                    "chunk_id": t["chunk_id"],
                    "doc": t["doc"],
                    "titulo": t["titulo"],
                    "pagina": t.get("pagina"),
                    "url": t["url"],
                    "referencia": _referencia(t),
                    "caracteristicas": [],
                    "aviso_de_uso": aviso_de_uso,
                    "trecho": t["trecho"],
                }
                por_trecho[t["chunk_id"]] = fonte
                fontes.append(fonte)
            if id_carac not in fonte["caracteristicas"]:
                fonte["caracteristicas"].append(id_carac)

    blocos = []
    for f in fontes:
        aviso = f"\nAVISO DE USO: {f['aviso_de_uso']}" if f["aviso_de_uso"] else ""
        blocos.append(
            f"[{f['rotulo']}] {f['referencia']}\nCaracterística: {', '.join(f['caracteristicas'])}{aviso}\n{f['trecho']}"
        )

    partes = ["CARACTERÍSTICAS ATIVADAS:\n" + "\n".join(linhas_caracteristicas)]
    if invariantes:
        partes.append("INVARIANTES CURRICULARES (não alterar):\n" + "\n".join(f"- {i}" for i in invariantes))
    partes.append("TRECHOS:\n\n" + "\n\n".join(blocos))
    partes.append(REGRAS_DE_CITACAO)
    return {
        "contexto": "\n\n".join(partes),
        "fontes": fontes,
        "caracteristicas": [b["id_caracteristica"] for b in buscas],
    }


def conferir_citacoes(diretiva: str, fontes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Conferência mecânica da diretiva: citações que não existem e frases sem citação.

    Não avalia se o trecho sustenta a frase; isso é a medida de fidelidade.
    """
    validos = {f["rotulo"] for f in fontes}
    citados = sorted(set(re.findall(r"\[(T\d+)\]", diretiva)), key=lambda r: int(r[1:]))
    blocos = re.split(r"(?<=[.!?])\s+|\n+", diretiva.strip())
    frases = [f.strip() for f in blocos if len(f.split()) >= 4]
    return {
        "citados": citados,
        "citacoes_inexistentes": [r for r in citados if r not in validos],
        "frases_sem_citacao": [f for f in frases if not re.search(r"\[T\d+\]", f)],
        "referencias": [f["referencia"] for f in fontes if f["rotulo"] in citados],
    }
