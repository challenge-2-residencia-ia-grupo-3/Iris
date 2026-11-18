"""Verificações de qualidade (a "bancada") servidas dentro do playground.

A página das verificações é gerada por ``rag/iris-rag/pacote/bancada.py`` numa página HTML única, que só lê arquivos já
gravados (o retrato em ``rag/iris-rag/bancada/referencia`` e as saídas em ``rag/iris-rag/pacote/outputs``): abrir não
roda verificação nem chama modelo. Este módulo só encontra essa página, gera de novo quando pedido e devolve o
conteúdo para as rotas ``/verificacoes/`` dos dois servidores.

A página é a mesma da bancada original (que veio do PR 85 do repositório do grupo), com um modo a mais (``?embutido=1``) que esconde o menu lateral dela: o menu fica no
playground, que abre uma aba de cada vez. Os botões de comando do painel original (rodar ``make`` pela página) ficam
de fora de propósito: no backend do produto, eles abririam um caminho para executar comando por requisição.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# backend/src/iris/eval -> raiz do repositório
RAIZ_REPO = Path(__file__).resolve().parents[4]
PACOTE = RAIZ_REPO / "rag" / "iris-rag" / "pacote"
GERADOR = PACOTE / "bancada.py"
PAGINA = PACOTE / "reports" / "bancada.html"
STATUS = PACOTE / "reports" / "status.json"  # só existe na cópia publicada pelo vigia da bancada

# As 22 telas da bancada, na ordem e nos grupos do menu original (SECOES em pacote/painel.py).
ABAS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Estado", [("visao", "Visão geral"), ("commits", "Commits e portões"), ("prs", "PRs e issues"),
                ("achados", "Achados")]),
    ("Código", [("grafo", "Grafo do código"), ("pipeline", "Pipeline inteiro"),
                ("arquitetura", "Arquitetura com LangGraph")]),
    ("RAG", [("rastro-sec", "Rastro do RAG"), ("llmxrag", "LLM x RAG"), ("qualidade", "Qualidade por versão"),
             ("confianca", "Reprodutibilidade e custo"), ("revisao", "Revisão humana")]),
    ("Qualidade", [("q-avaliacao", "Conjunto de avaliação"), ("q-rag", "RAG: os quatro elos"),
                   ("q-ataque", "Ataque em massa"), ("q-juiz", "Juízes x pessoas"),
                   ("q-orcamento", "Orçamento RNF-07"), ("q-producao", "Produção")]),
    ("Testes", [("seguranca", "Segurança e ablação"), ("comandos", "Comandos")]),
    ("Guia", [("mapa-painel", "Mapa do painel"), ("ferramentas", "Ferramentas")]),
]


# Telas da bancada que ficam fora do menu, por decisão de 16/11/2026 (comparativo em docs/rag/painel_qualidade_comparativo.md).
# O código delas continua no repositório: voltar uma tela é tirar a linha daqui e pôr o botão no playground.
FORA_DO_MENU: dict[str, str] = {
    "prs": "o dado é um retrato de 13/11; volta quando puder se atualizar sozinho",
    "arquitetura": "fica a aba Arquitetura (LangGraph) do playground, que roda com o material do professor",
    "q-ataque": "fica o ataque das Ferramentas da API, que mede o removedor atual",
    "q-producao": "testa uma proposta que ainda não está no produto",
    "comandos": "o botão Medir de novo sem modelo cobre o que roda pela página; os comandos ficam no README da bancada",
    "mapa-painel": "cada aba já abre com a pergunta da tela",
}


def abas_no_menu() -> list[tuple[str, list[tuple[str, str]]]]:
    """As telas da bancada que aparecem no menu do playground, nos grupos originais."""
    out = []
    for grupo, itens in ABAS:
        ficam = [(i, n) for i, n in itens if i not in FORA_DO_MENU]
        if ficam:
            out.append((grupo, ficam))
    return out


# Só o próprio computador vê as telas de verificação: a página leva trechos de documentos sem licença aberta.
CAMINHOS_PROTEGIDOS = ("/verificacoes", "/api/v1/eval/verificacoes-qualidade", "/api/v1/eval/avaliacao-humana")
ENDERECOS_LOCAIS = {"127.0.0.1", "::1", "localhost"}
CABECALHOS_DE_PROXY = ("x-forwarded-for", "x-real-ip", "forwarded")
MENSAGEM_SO_LOCAL = ("As telas de verificação de qualidade só abrem no próprio computador (127.0.0.1): a página leva trechos de "
                     "documentos sem licença aberta.")


def caminho_protegido(caminho: str) -> bool:
    return any(caminho == c or caminho.startswith(c + "/") or caminho.startswith(c + "?") for c in CAMINHOS_PROTEGIDOS)


def pedido_local(endereco: str | None, cabecalhos: Any) -> bool:
    """O pedido veio do próprio computador, sem passar por um proxy?

    Atrás de um proxy reverso todo pedido parece vir de 127.0.0.1; por isso qualquer cabeçalho de proxy recusa.
    """
    if (endereco or "") not in ENDERECOS_LOCAIS:
        return False
    nomes = {str(k).lower() for k in (cabecalhos.keys() if hasattr(cabecalhos, "keys") else [])}
    return not any(h in nomes for h in CABECALHOS_DE_PROXY)


def disponivel() -> bool:
    """O código da bancada está neste repositório?"""
    return GERADOR.exists()


def gerar_pagina(tempo_limite_s: int = 300) -> dict[str, Any]:
    """Roda o gerador da bancada (``bancada.py html``) e devolve a última linha que ele imprime.

    O gerador só lê arquivos e escreve ``reports/bancada.html``; não chama modelo nem rede.
    """
    if not disponivel():
        return {"ok": False, "erro": f"não achei {_relativo(GERADOR)} neste repositório"}
    inicio = time.monotonic()
    proc = subprocess.run(  # comando fixo, sem entrada do usuário
        [sys.executable, str(GERADOR), "html"],
        cwd=str(PACOTE),
        capture_output=True,
        text=True,
        timeout=tempo_limite_s,
        check=False,
    )
    linhas = [l for l in (proc.stdout or "").splitlines() if l.strip()]
    return {
        "ok": proc.returncode == 0 and PAGINA.exists(),
        "codigo": proc.returncode,
        "segundos": round(time.monotonic() - inicio, 1),
        "resumo": linhas[-1] if linhas else "",
        "erro": (proc.stderr or "").strip()[-800:] if proc.returncode else "",
    }


def medir_de_novo(tempo_limite_s: int = 900) -> dict[str, Any]:
    """Roda as verificações de qualidade sem modelo contra o código deste repositório e gera a página de novo.

    É o alvo ``verificar`` de ``rag/iris-rag/pacote/Makefile``: pipeline com provedor determinístico (``eco``),
    bateria adversarial, ablação, mapa do código, etapas, conjunto de avaliação, ataque, orçamento, produção,
    portões e o grafo LangGraph. Não chama modelo nem rede; a chave de API é tirada do ambiente por garantia. As
    telas medidas com modelo (juízes, LLM x RAG) continuam vindo do retrato.
    """
    if not disponivel():
        return {"ok": False, "erro": f"não achei {_relativo(GERADOR)} neste repositório"}
    import os
    import shutil

    make = shutil.which("make")
    if not make:
        return {"ok": False, "erro": "o comando make não está instalado; rode as verificações pelo terminal"}
    ambiente = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    inicio = time.monotonic()
    proc = subprocess.run(  # comando fixo, sem entrada do usuário
        [make, "-C", str(PACOTE), "verificar", f"PY={sys.executable}", f"PYB={sys.executable}",
         f"GRUPO={RAIZ_REPO}", "PROV=eco"],
        capture_output=True,
        text=True,
        timeout=tempo_limite_s,
        check=False,
        env=ambiente,
    )
    linhas = [l for l in (proc.stdout or "").splitlines() if l.strip()]
    resumo = next((l for l in reversed(linhas) if "reports/bancada.html:" in l), linhas[-1] if linhas else "")
    return {
        "ok": proc.returncode == 0 and PAGINA.exists(),
        "codigo": proc.returncode,
        "segundos": round(time.monotonic() - inicio, 1),
        "resumo": resumo,
        "erro": ((proc.stderr or "") + "\n" + "\n".join(linhas[-8:])).strip()[-1200:] if proc.returncode else "",
    }


def ler_pagina(embutido: bool = False) -> str:
    """O HTML das verificações; gera na primeira vez se ainda não existir.

    Com ``embutido=True`` (a página aberta dentro do playground), ajusta o desenho para ficar igual ao da bancada
    aberta sozinha: ver ``ajustar_para_embutir``.
    """
    if not PAGINA.exists():
        r = gerar_pagina()
        if not r["ok"]:
            return _pagina_de_erro(r.get("erro") or "o gerador terminou sem criar a página")
    pagina = PAGINA.read_text(encoding="utf-8")
    return ajustar_para_embutir(pagina) if embutido else pagina


# Largura do menu lateral da bancada aberta sozinha; dentro do playground ele não aparece.
LARGURA_MENU_BANCADA = 244
RE_MEDIA = re.compile(r"@media\s*\(\s*max-width\s*:\s*(\d+)px\s*\)")
RE_VH = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)vh\b")


def ajustar_para_embutir(pagina: str) -> str:
    """Dois ajustes para a página dentro do playground ficar com o mesmo desenho da bancada aberta sozinha.

    1. Os pontos de troca de desenho (``@media (max-width: N px)``) da bancada contam a largura da janela, que inclui
       o menu lateral de 244 px. Dentro do playground o menu não existe e o quadro tem só a largura do conteúdo; sem
       o ajuste, a tela acha que está numa janela menor e empilha cartões que ficavam lado a lado. Os pontos acima de
       900 px (onde o menu ainda fica ao lado) descem 244 px; os de 900 px para baixo valem para a tela inteira e
       ficam como estão.
    2. O quadro cresce até a altura do conteúdo (sem rolagem dentro dele). O que era medido pela altura da janela
       (``vh``: o grafo do código, os detalhes laterais) passa a usar a altura da janela do playground, que ele
       informa em ``--vhp``; sem isso, a altura cresceria junto com o quadro, sem parar.
    O bloco de dados (``const DADOS=``) não é tocado.
    """
    marca = "<script>const DADOS="
    i = pagina.find(marca)
    j = pagina.find("</script>", i) if i >= 0 else -1
    if i < 0 or j < 0:
        return pagina

    def ajusta(trecho: str) -> str:
        def media(m: re.Match) -> str:
            n = int(m.group(1))
            return f"@media (max-width:{n - LARGURA_MENU_BANCADA}px)" if n > 900 else m.group(0)

        return RE_VH.sub(lambda m: f"calc(var(--vhp, 8px) * {m.group(1)})", RE_MEDIA.sub(media, trecho))

    return ajusta(pagina[:i]) + pagina[i:j] + ajusta(pagina[j:])


def ler_status() -> bytes | None:
    """``status.json`` da cópia publicada, quando existe (a página consulta a cada minuto; sem ele, segue parada)."""
    return STATUS.read_bytes() if STATUS.exists() else None


def descrever() -> dict[str, Any]:
    """O que o playground precisa para montar o menu: as abas e se a página já foi gerada."""
    return {
        "disponivel": disponivel(),
        "gerada": PAGINA.exists(),
        "gerada_em": time.strftime("%d/%m/%Y %H:%M", time.localtime(PAGINA.stat().st_mtime)) if PAGINA.exists() else None,
        "abas": [{"grupo": g, "abas": [{"id": i, "nome": n} for i, n in itens]} for g, itens in abas_no_menu()],
        "fora_do_menu": FORA_DO_MENU,
    }


def _relativo(caminho: Path) -> str:
    """Caminho a partir da raiz do repositório quando der; senão, o caminho inteiro."""
    try:
        return str(caminho.relative_to(RAIZ_REPO))
    except ValueError:
        return str(caminho)


def _pagina_de_erro(msg: str) -> str:
    from html import escape

    return (
        "<!doctype html><meta charset=utf-8><title>Verificações de qualidade</title>"
        "<body style='font:14px system-ui;padding:24px'><h1 style='font-size:18px'>A página das verificações de qualidade "
        f"não foi gerada</h1><pre style='white-space:pre-wrap'>{escape(msg)}</pre>"
        "<p>Para gerar à mão: <code>cd rag/iris-rag/pacote && python bancada.py html</code></p></body>"
    )
