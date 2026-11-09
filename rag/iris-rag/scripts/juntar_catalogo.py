"""Junta os quatro catálogos de curadoria (partes A a D) num único fontes.json e gera FONTES.md.

uso:  python3 scripts/juntar_catalogo.py      (rodar na raiz iris-rag/)

Regras de entrada no índice (decididas por quem montou a base, registradas em cada documento):
- status 'aceito' e texto extraído presente;
- quase duplicata NÃO entra no índice (fica no catálogo, com 'quase_duplicata_de'):
    CAST-UDL-GUIDELINES-3-0-2024 (inglês) -> mesma versão 3.0 em português (texto completo)
    CAST-DUA-3-0-ORGANIZADOR-PTBR-2024 (1 página-resumo) -> o texto completo em português
  Motivo: a busca por sentido entende as duas línguas; indexar as duas faria a mesma consideração
  do DUA ocupar 2 das 5 vagas do top-5.
- avisos de uso ('nota_uso'): versão antiga do DUA (2.0), norma parcialmente substituída, cartilha sem referências.
"""
import json
from pathlib import Path

PARTES = {
    "A": ("fontes_A_dua.json", "DUA"),
    "B": ("fontes_B_funcoes_executivas.json", "TDAH e funções executivas"),
    "C": ("fontes_C_normas_mec.json", "Normas e MEC"),
    "D": ("fontes_D_pesquisa.json", "Pesquisa acadêmica"),
}
QUASE_DUPLICATAS = {
    "CAST-UDL-GUIDELINES-3-0-2024": "CAST-DUA-3-0-TEXTO-COMPLETO-PTBR-2024",
    "CAST-DUA-3-0-ORGANIZADOR-PTBR-2024": "CAST-DUA-3-0-TEXTO-COMPLETO-PTBR-2024",
}
NOTAS_EXTRA = {
    "RBEE-SEBASTIAN-HEREDERO-2020-DIRETRIZES-DUA":
        "Tradução das Diretrizes DUA versão 2.0 (2018). Para a numeração e o texto dos pontos de verificação, prevalece a versão 3.0 (CAST 2024).",
    "MEC-POLITICA-PEEI-2008":
        "Política de 2008 usada só como referência conceitual; a política vigente é o Decreto 12.686/2025 e a Portaria MEC 421/2026.",
    "ABDA-GUIA-PROFESSORES-2012":
        "Cartilha sem referências: serve para linguagem com o professor, não como evidência de eficácia.",
    "RES-CNE-CEB-4-2009-AEE":
        "Resolução de 2009 com termos antigos; em conflito, prevalecem o Decreto 12.686/2025 e a Portaria MEC 421/2026.",
}
CAMPOS = ["id", "parte", "parte_nome", "titulo", "autores", "orgao", "revista", "ano", "url", "doi", "data_acesso",
          "licenca", "idioma", "tipo", "paginas", "caracteres_extraidos", "sha256_bruto", "bytes_bruto",
          "arquivo_bruto", "arquivo_texto", "tema", "barreiras", "tipo_evidencia", "publico", "vigencia", "bloco",
          "achado_principal", "implicacao_para_iris", "por_que_entra", "qualidade_extracao", "obs_qualidade",
          "nota_uso", "quase_duplicata_de", "status"]


def ano_de(x):
    return str(x.get("ano") or x.get("ano_edicao") or "")


def main():
    docs, recusados, nao_obtidos = [], [], []
    for letra, (arq, nome) in PARTES.items():
        d = json.loads(Path(arq).read_text(encoding="utf-8"))
        for x in d["documentos"]:
            y = {k: x.get(k) for k in CAMPOS}
            y["parte"], y["parte_nome"], y["ano"] = letra, nome, ano_de(x)
            y["idioma"] = "pt-BR" if (x.get("idioma") or "").lower().startswith("pt") else x.get("idioma")
            if isinstance(y["autores"], list):
                y["autores"] = "; ".join(y["autores"])
            y["tema"] = list(x.get("tema") or [])
            y["barreiras"] = list(x.get("barreiras") or [])
            notas = [n for n in [x.get("nota_uso"), NOTAS_EXTRA.get(x["id"])] if n]
            y["nota_uso"] = " ".join(notas)
            y["quase_duplicata_de"] = QUASE_DUPLICATAS.get(x["id"])
            if not Path(x["arquivo_texto"]).exists():
                y["status"] = "sem_texto"
            docs.append(y)
        recusados += [dict(r, parte=letra) for r in d.get("recusados", [])]
        nao_obtidos += [dict(r, parte=letra) for r in d.get("nao_obtidos", [])]
    ids = [x["id"] for x in docs]
    assert len(ids) == len(set(ids)), "id repetido entre as partes"
    indexados = [x for x in docs if x["status"] == "aceito" and not x["quase_duplicata_de"]]
    out = {"gerado_em": "2026-11-04", "n_documentos": len(docs), "n_indexados": len(indexados),
           "documentos": docs, "recusados": recusados, "nao_obtidos": nao_obtidos}
    Path("fontes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    L = ["# Fontes da base do Íris", "",
         f"{len(docs)} documentos aceitos na curadoria; **{len(indexados)} entram no índice** "
         f"({len(docs) - len(indexados)} ficam só no catálogo como quase duplicata). "
         f"{len(recusados)} recusados e {len(nao_obtidos)} não obtidos estão listados no fim.", "",
         "Gerado por `scripts/juntar_catalogo.py` a partir de `fontes_A..D_*.json`. Acesso em 04/11/2026.", ""]
    for letra, (_, nome) in PARTES.items():
        parte = [x for x in docs if x["parte"] == letra]
        L += [f"## {letra}. {nome} ({len(parte)})", "",
              "| id | título | ano | idioma | evidência | licença | índice |", "|---|---|---|---|---|---|---|"]
        for x in parte:
            ind = "não (quase duplicata)" if x["quase_duplicata_de"] else ("sim" if x["status"] == "aceito" else x["status"])
            tit = (x["titulo"] or "").replace("|", "/")
            L.append(f"| `{x['id']}` | [{tit[:90]}]({x['url']}) | {x['ano']} | {x['idioma']} | "
                     f"{x.get('tipo_evidencia') or x.get('vigencia') or '-'} | {(x['licenca'] or '')[:60]} | {ind} |")
        L.append("")
    L += ["## Recusados", "", "| parte | id | motivo |", "|---|---|---|"]
    L += [f"| {r['parte']} | {r.get('id', '-')} | {str(r.get('motivo', ''))[:160]} |" for r in recusados]
    L += ["", "## Não obtidos", "", "| parte | o quê | erro |", "|---|---|---|"]
    for r in nao_obtidos:
        oque = r.get("id") or r.get("titulo") or r.get("o_que") or r.get("descricao") or "-"
        L.append(f"| {r['parte']} | {str(oque)[:90]} | {str(r.get('erro') or r.get('motivo') or '')[:120]} |")
    Path("FONTES.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(docs)} documentos ({len(indexados)} indexados), {len(recusados)} recusados, {len(nao_obtidos)} não obtidos")


if __name__ == "__main__":
    main()
