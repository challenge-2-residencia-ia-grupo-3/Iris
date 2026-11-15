"""Ataque de dado pessoal ao removedor `sanitize_pii` (RNF-02 / LGPD).

Pergunta: se um professor colar uma atividade com um dado pessoal, o dado sai antes de o texto seguir adiante?

Como o teste é feito: o mesmo dado inventado é escrito de várias formas (tipo do dado, rótulo que o antecede
e posição no material), o texto passa por `sanitize_pii` e conta-se em quantos casos o dado continua legível
na saída. Nenhum modelo é chamado: é contagem sobre texto.

Todos os valores são fictícios e reconhecíveis como tal (DDD 00, domínio `exemplo.test`, nomes de teste).
O sorteio tem semente fixa, então a mesma versão do removedor dá sempre o mesmo resultado.

Dois grupos de tipo:
- `prometido`: o que o módulo do grupo diz remover (estudante, professor, CPF, matrícula, telefone, e-mail).
- não prometido: dado pessoal que o módulo não cita (RG, data de nascimento, endereço, responsável).
  Vazamento aqui não é promessa quebrada; é o tamanho do que fica de fora.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from iris.config import REPO_ROOT
from iris.security.pii_scrubber import sanitize_pii

ATAQUE_PII_PADRAO = REPO_ROOT / "reports" / "ataque_pii.json"
SEMENTE = 20261115
REPETICOES = 2
MAX_EXEMPLOS = 12

PRIMEIROS = ["Fulano", "Beltrana", "Ciclano", "Zuleide", "Teodoro"]
SOBRENOMES = ["Ficticio", "Inventado", "Imaginario", "Testeira"]
NOMES_ACENTO = ["Joãozinho Fictício", "Mariângela Inventária", "Tomé Imaginário"]

TITULO = "Atividade de Ciências - 6º ano B"
ENUNCIADO = (
    "Questão 1: Leia o texto sobre o ciclo da água, identifique suas etapas principais e explique o papel "
    "da evaporação."
)
ENUNCIADO_2 = "Questão 2: Qual é a diferença entre condensação e precipitação?"

# Enunciados sem nenhum dado pessoal. O removedor não pode apagar o trecho protegido.
CONTROLES = [
    ("numero_grande", "Questão 3: A população da cidade passou de 1250000 para 1375000 habitantes em 2020.", "1375000"),
    ("ano_e_data", "Questão 4: A Lei Áurea foi assinada em 13 de maio de 1888.", "13 de maio de 1888"),
    ("nome_historico", "Questão 5: Explique o papel de Dom Pedro II na Guerra do Paraguai.", "Dom Pedro II"),
    ("conta", "Questão 6: Calcule 3482 - 1957 e depois multiplique o resultado por 12.", "3482 - 1957"),
    ("escola_no_texto", "Questão 7: Descreva como a escola pode reduzir o desperdício de água.", "a escola pode reduzir"),
    ("aluno_no_texto", "Questão 8: Um aluno mediu 2,75 metros de corda. Quantos centímetros são?", "Um aluno mediu 2,75 metros"),
    ("isbn", "Questão 9: Procure na biblioteca o livro de ISBN 9788535902778 e leia o capítulo 2.", "9788535902778"),
    ("codigo_longo", "Questão 10: O código de barras do produto é 7891234567895. Quantos dígitos ele tem?", "7891234567895"),
    ("intervalo_de_anos", "Questão 11: A obra de Frei Vicente de Salvador (1564-1633) foi publicada em 1627. Comente.", "1564-1633"),
]


def _cpf_falso(rng: random.Random, pontuado: bool) -> str:
    # Começa com 000: não é CPF de ninguém; os dígitos verificadores são sorteados, não calculados.
    d = "000" + "".join(str(rng.randint(0, 9)) for _ in range(8))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if pontuado else d


def _nome(rng: random.Random) -> str:
    return f"{rng.choice(PRIMEIROS)} {rng.choice(SOBRENOMES)}"


# tipo -> (rótulo legível, família, prometido pelo módulo, gerador do valor)
TIPOS: dict[str, tuple[str, str, bool, Callable[[random.Random], str]]] = {
    "nome_estudante": ("Nome do estudante", "nome", True, _nome),
    "nome_caixa_alta": ("Nome em caixa alta", "nome", True, lambda r: _nome(r).upper()),
    "nome_com_acento": ("Nome com acento", "nome", True, lambda r: r.choice(NOMES_ACENTO)),
    "nome_professor": ("Nome do professor", "nome", True, _nome),
    "cpf_pontuado": ("CPF com pontos", "documento", True, lambda r: _cpf_falso(r, True)),
    "cpf_sem_pontuacao": ("CPF só com dígitos", "documento", True, lambda r: _cpf_falso(r, False)),
    "matricula": ("Matrícula", "documento", True, lambda r: f"2026-FIC-{r.randint(1000, 9999)}"),
    "telefone": ("Telefone celular", "contato", True, lambda r: f"(00) 9{r.randint(1000, 9999)}-{r.randint(1000, 9999)}"),
    "email": ("E-mail", "contato", True, lambda r: f"{r.choice(PRIMEIROS).lower()}.teste{r.randint(10, 99)}@exemplo.test"),
    "rg": ("RG", "documento", False, lambda r: f"{r.randint(10, 99)}.{r.randint(100, 999)}.{r.randint(100, 999)}-{r.randint(0, 9)}"),
    "data_nascimento": ("Data de nascimento", "documento", False, lambda r: f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}/{r.randint(2010, 2016)}"),
    "endereco": ("Endereço", "contato", False, lambda r: f"Rua Ficticia das Flores, {r.randint(10, 999)}, Bairro Inventado"),
    "nome_responsavel": ("Nome do responsável", "nome", False, _nome),
}

# tipo -> o rótulo que antecede o dado, em quatro grafias
ROTULOS: dict[str, dict[str, str]] = {
    "nome": {"pt": "Aluno:", "en": "Student:", "abrev": "Al.:", "sem": ""},
    "nome_professor": {"pt": "Professor:", "en": "Teacher:", "abrev": "Prof.ª", "sem": ""},
    "nome_responsavel": {"pt": "Responsável:", "en": "Parent:", "abrev": "Resp.:", "sem": ""},
    "cpf": {"pt": "CPF:", "en": "Tax ID:", "abrev": "C.P.F.", "sem": ""},
    "matricula": {"pt": "Matrícula:", "en": "Student ID:", "abrev": "Mat.:", "sem": ""},
    "telefone": {"pt": "Telefone:", "en": "Phone:", "abrev": "Tel.:", "sem": ""},
    "email": {"pt": "E-mail:", "en": "Email:", "abrev": "e-m.:", "sem": ""},
    "rg": {"pt": "RG:", "en": "ID card:", "abrev": "Ident.:", "sem": ""},
    "data_nascimento": {"pt": "Data de nascimento:", "en": "Date of birth:", "abrev": "Nasc.:", "sem": ""},
    "endereco": {"pt": "Endereço:", "en": "Address:", "abrev": "End.:", "sem": ""},
}
NOME_ROTULO = {"pt": "Rótulo em português", "en": "Rótulo em inglês", "abrev": "Rótulo abreviado", "sem": "Sem rótulo"}
POSICOES = {"cabecalho": "Cabeçalho", "meio": "No meio da frase", "rodape": "Rodapé", "lista": "Item de lista"}


def _chave_rotulo(tipo: str) -> str:
    if tipo in ROTULOS:
        return tipo
    if tipo.startswith("cpf"):
        return "cpf"
    return "nome"


def montar_material(tipo: str, rotulo: str, posicao: str, valor: str) -> str:
    """Escreve o material com o dado no lugar pedido. O enunciado ao redor é sempre o mesmo."""
    campo = f"{ROTULOS[_chave_rotulo(tipo)][rotulo]} {valor}".strip()
    if posicao == "cabecalho":
        return f"{TITULO}\n{campo}\n\n{ENUNCIADO}\n{ENUNCIADO_2}"
    if posicao == "meio":
        return f"{TITULO}\n\n{ENUNCIADO} Atenção para o caso de {campo} antes de corrigir.\n{ENUNCIADO_2}"
    if posicao == "rodape":
        return f"{TITULO}\n\n{ENUNCIADO}\n{ENUNCIADO_2}\n\n{campo}"
    if posicao == "lista":
        return f"{TITULO}\n\nDados da turma:\n- Turno: manhã\n- {campo}\n\n{ENUNCIADO}\n{ENUNCIADO_2}"
    raise ValueError(f"Posição desconhecida: {posicao!r}")


def _visao(texto: str) -> str:
    """Como um leitor enxerga o texto: sem acento, minúsculo, espaços normalizados."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.casefold())


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def vazou(valor: str, tipo: str, saida: str, fundo: str) -> bool:
    """O dado sobreviveu ao removedor? Conta também o pedaço que ainda identifica.

    `fundo` é o material sem o dado: palavra ou número que já estava no enunciado não conta como vazamento.
    """
    vs, vv = _visao(saida), _visao(valor)
    if vv in vs:
        return True
    familia = TIPOS[tipo][1]
    if familia == "nome":
        ja_estava = set(re.findall(r"\w+", _visao(fundo)))
        return any(
            len(p) >= 4 and p not in ja_estava and re.search(rf"\b{re.escape(p)}\b", vs) for p in vv.split()
        )
    if tipo == "email":
        local = vv.split("@")[0]
        return len(local) >= 4 and local in vs
    if tipo == "endereco":
        return "ficticia das flores" in vs or "bairro inventado" in vs
    alvo = _digitos(valor)
    if tipo == "telefone" and alvo.startswith("00"):
        alvo = alvo[2:]  # o DDD 00 é inventado; o que identifica é o número
    if len(alvo) < 7:
        return False
    corridas_fundo = {_digitos(c) for c in re.findall(r"\d[\d.\-\s/]*\d", fundo)}
    corridas = [_digitos(c) for c in re.findall(r"\d[\d.\-\s/]*\d", saida)]
    return any(c not in corridas_fundo and (alvo in c or (len(c) >= 7 and c in alvo)) for c in corridas)


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Intervalo de 95% para uma proporção (Wilson): não sai de 0 a 100 nem colapsa em 0 de n."""
    if n == 0:
        return None
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centro - meia) * 100.0, 1), round(min(1.0, centro + meia) * 100.0, 1)]


def _taxa(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(linhas)
    k = sum(1 for linha in linhas if linha["vazou"])
    return {"vazou": k, "total": n, "taxa_pct": round((k / n) * 100.0, 1) if n else None, "ic95": wilson(k, n)}


def gerar_casos(semente: int = SEMENTE, repeticoes: int = REPETICOES) -> list[dict[str, Any]]:
    """Todos os cruzamentos de tipo, rótulo e posição, com `repeticoes` valores sorteados cada."""
    rng = random.Random(semente)
    casos: list[dict[str, Any]] = []
    for tipo, (_, _, prometido, gerar) in TIPOS.items():
        for rotulo in NOME_ROTULO:
            for posicao in POSICOES:
                for rep in range(repeticoes):
                    valor = gerar(rng)
                    casos.append(
                        {
                            "id": f"{tipo}/{rotulo}/{posicao}/{rep + 1}",
                            "tipo": tipo,
                            "rotulo": rotulo,
                            "posicao": posicao,
                            "prometido": prometido,
                            "valor": valor,
                            "texto": montar_material(tipo, rotulo, posicao, valor),
                        }
                    )
    return casos


FORMATOS = {"texto": "Texto colado", "docx": "Arquivo .docx", "pdf": "Arquivo .pdf"}


def montar_arquivo(formato: str, texto: str) -> bytes:
    """Escreve o material como arquivo de verdade, uma linha por parágrafo, para passar pelo extrator do grupo."""
    import io

    if formato == "docx":
        import docx

        documento = docx.Document()
        for linha in texto.splitlines():
            documento.add_paragraph(linha)
        saida = io.BytesIO()
        documento.save(saida)
        return saida.getvalue()
    if formato == "pdf":
        try:
            import pymupdf as fitz
        except ImportError:  # versões antigas só têm o nome fitz
            import fitz  # type: ignore[no-redef]

        doc = fitz.open()
        pagina = doc.new_page()
        sobra = pagina.insert_textbox(fitz.Rect(50, 50, 545, 800), texto, fontsize=10, fontname="helv")
        if sobra < 0:
            raise ValueError("o material não coube numa página do PDF de teste")
        dados = doc.tobytes()
        doc.close()
        return dados
    raise ValueError(f"Formato desconhecido: {formato!r}")


def _texto_extraido(formato: str, texto: str) -> str:
    """O texto que o removedor recebe: o próprio texto colado, ou o que o extrator do grupo tira do arquivo."""
    if formato == "texto":
        return texto
    from iris.parsers.document_extractor import extract_text_from_file

    extraido, _ = extract_text_from_file(f"material.{formato}", montar_arquivo(formato, texto))
    return extraido


def _assinatura(casos: list[dict[str, Any]]) -> str:
    bruto = json.dumps([[c["id"], c["texto"]] for c in casos], ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()[:16]


def executar_ataque_pii(
    *,
    sanitizar: Callable[[str], tuple[str, int]] = sanitize_pii,
    semente: int = SEMENTE,
    repeticoes: int = REPETICOES,
    caminho_saida: str | Path | None = None,
    salvar: bool = True,
    formatos: tuple[str, ...] = ("docx", "pdf"),
) -> dict[str, Any]:
    """Roda o ataque e devolve as taxas de vazamento por tipo, por rótulo e por posição.

    Os números principais são os do texto colado. `formatos` repete os mesmos casos escritos como arquivo e lidos
    pelo extrator do grupo (`extract_text_from_file`) antes do removedor; o resultado vai em `por_formato`.
    """
    casos = gerar_casos(semente, repeticoes)
    linhas: list[dict[str, Any]] = []
    for caso in casos:
        saida, _ = sanitizar(caso["texto"])
        fundo = caso["texto"].replace(caso["valor"], " ")
        linhas.append({**caso, "saida": saida, "vazou": vazou(caso["valor"], caso["tipo"], saida, fundo)})

    por_formato: dict[str, Any] = {}
    for formato in ("texto", *formatos):
        if formato == "texto":
            linhas_f = linhas
        else:
            linhas_f = []
            for caso in casos:
                saida, _ = sanitizar(_texto_extraido(formato, caso["texto"]))
                fundo = caso["texto"].replace(caso["valor"], " ")
                linhas_f.append({**caso, "vazou": vazou(caso["valor"], caso["tipo"], saida, fundo)})
        por_formato[formato] = {
            "nome": FORMATOS[formato],
            **_taxa(linhas_f),
            "prometidos": _taxa([x for x in linhas_f if x["prometido"]]),
            "prometidos_rotulo_pt": _taxa([x for x in linhas_f if x["prometido"] and x["rotulo"] == "pt"]),
            "por_tipo": {t: _taxa([x for x in linhas_f if x["tipo"] == t]) for t in TIPOS},
        }

    controles: list[dict[str, Any]] = []
    for nome, enunciado, protegido in CONTROLES:
        saida, substituicoes = sanitizar(f"{TITULO}\n\n{enunciado}")
        controles.append(
            {
                "id": nome,
                "enunciado": enunciado,
                "protegido": protegido,
                "apagou": _visao(protegido) not in _visao(saida),
                "substituicoes": substituicoes,
                "saida": saida,
            }
        )

    prometidos = [linha for linha in linhas if linha["prometido"]]
    nao_prometidos = [linha for linha in linhas if not linha["prometido"]]
    por_tipo = {
        tipo: {
            "nome": TIPOS[tipo][0],
            "prometido": TIPOS[tipo][2],
            **_taxa([linha for linha in linhas if linha["tipo"] == tipo]),
            "por_rotulo": {r: _taxa([x for x in linhas if x["tipo"] == tipo and x["rotulo"] == r]) for r in NOME_ROTULO},
        }
        for tipo in TIPOS
    }
    vazados = [linha for linha in linhas if linha["vazou"]]
    vistos: set[tuple[str, str]] = set()
    exemplos: list[dict[str, Any]] = []
    for linha in sorted(vazados, key=lambda x: (not x["prometido"], x["rotulo"] != "pt", x["id"])):
        chave = (linha["tipo"], linha["rotulo"])
        if chave in vistos or len(exemplos) >= MAX_EXEMPLOS:
            continue
        vistos.add(chave)
        trecho = next((t for t in linha["saida"].splitlines() if _visao(linha["valor"].split()[0]) in _visao(t)), "")
        exemplos.append(
            {
                "id": linha["id"],
                "tipo": TIPOS[linha["tipo"]][0],
                "rotulo": NOME_ROTULO[linha["rotulo"]],
                "posicao": POSICOES[linha["posicao"]],
                "prometido": linha["prometido"],
                "linha_da_saida": (trecho or linha["saida"])[:200],
            }
        )

    relatorio = {
        "ataque_id": f"ataque-pii-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "semente": semente,
        "repeticoes": repeticoes,
        "assinatura_casos": _assinatura(casos),
        "valores_ficticios": True,
        "geral": _taxa(linhas),
        "prometidos": _taxa(prometidos),
        "prometidos_rotulo_pt": _taxa([linha for linha in prometidos if linha["rotulo"] == "pt"]),
        "nao_prometidos": _taxa(nao_prometidos),
        "por_tipo": por_tipo,
        "por_rotulo": {r: {"nome": NOME_ROTULO[r], **_taxa([x for x in linhas if x["rotulo"] == r])} for r in NOME_ROTULO},
        "por_posicao": {p: {"nome": POSICOES[p], **_taxa([x for x in linhas if x["posicao"] == p])} for p in POSICOES},
        "controles": {
            "total": len(controles),
            "apagou_conteudo": sum(1 for c in controles if c["apagou"]),
            "itens": controles,
        },
        "exemplos": exemplos,
        "rotulos": NOME_ROTULO,
        "por_formato": por_formato,
    }
    if salvar:
        destino = Path(caminho_saida) if caminho_saida else ATAQUE_PII_PADRAO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"tem_ataque": True, **relatorio}


def obter_ataque_pii(caminho_saida: str | Path | None = None) -> dict[str, Any]:
    """Devolve o último ataque gravado, ou só o tamanho do ataque quando ainda não há nenhum."""
    total = len(TIPOS) * len(NOME_ROTULO) * len(POSICOES) * REPETICOES
    origem = Path(caminho_saida) if caminho_saida else ATAQUE_PII_PADRAO
    if origem.exists():
        try:
            return {"tem_ataque": True, "total_casos": total, **json.loads(origem.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            pass
    return {"tem_ataque": False, "total_casos": total, "total_controles": len(CONTROLES)}
