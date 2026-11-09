"""Gera diagrama_arquitetura.svg: fluxos de ingestão e de consulta e processo de avaliação.

    python scripts_dev/gerar_diagrama.py

O SVG é montado sem dependências externas e pode ser aberto em qualquer navegador.
"""
from pathlib import Path

L, A = 1200, 600                       # largura e altura do desenho
MARGEM, VAO, N = 40, 18, 6             # margem lateral, vão entre caixas, caixas por faixa
LARG = (L - 2 * MARGEM - (N - 1) * VAO) / N
ALT = 112
COR = {"ingestao": ("#0f766e", "#f0fdfa"), "consulta": ("#1d4ed8", "#eff6ff"), "medida": ("#6b7280", "#f9fafb")}

FAIXAS = [
    ("INGESTÃO (a cada alteração da base)", "ingestao", 70, [
        ("1. Curadoria", ["38 documentos em 4 partes", "fonte primária ou oficial", "licença e SHA-256 anotados"]),
        ("2. Extração", ["PDF, HTML, DOCX e leis", "marcação de página", "sem texto revogado"]),
        ("3. Segmentação", ["corte por título ou artigo", "até 350 palavras", "1.368 trechos"]),
        ("4. Metadados", ["documento, página, seção", "idioma, tipo de evidência", "aviso de uso"]),
        ("5. Embeddings", ["Qwen3: 1.024 dimensões", "MPNet: 768 dimensões", "BM25 em memória"]),
        ("6. Banco vetorial", ["PostgreSQL 17 + pgvector", "tabela iris_trechos", "texto, metadados e vetores"]),
    ]),
    ("CONSULTA (a cada requisição)", "consulta", 290, [
        ("1. Consulta", ["professor ou", "Agente Estrategista"]),
        ("2. Vetorização", ["Qwen3, com", "instrução de busca"]),
        ("3. Busca vetorial", ["50 trechos mais similares", "distância de cosseno", "consulta SQL"]),
        ("4. Reordenação", ["cross-encoder avalia cada", "par consulta–trecho;", "seleciona 5"]),
        ("5. Geração", ["restrita aos 5 trechos", "citação por frase", "recusa por insuficiência"]),
        ("6. Evidência", ["documento, página e", "endereço por frase", "citações verificadas"]),
    ]),
]
MEDIDA = ("AVALIAÇÃO (fora do fluxo de resposta)", 470, [
    ("Conjunto de referência", ["40 consultas elaboradas antes da busca;", "trechos relevantes identificados por modelo"]),
    ("Recuperação", ["recall@5 e consultas com ao menos", "um trecho relevante entre os 5"]),
    ("Respostas", ["dois avaliadores automáticos classificam cada", "frase e transcrevem a passagem do trecho"]),
])


def caixa(x, y, larg, alt, titulo, linhas, tipo):
    borda, fundo = COR[tipo]
    s = [f'<rect x="{x:.0f}" y="{y}" width="{larg:.0f}" height="{alt}" rx="8" fill="{fundo}" stroke="{borda}" stroke-width="1.5"/>',
         f'<text x="{x + 12:.0f}" y="{y + 24}" font-size="14" font-weight="600" fill="#111827">{titulo}</text>']
    for i, l in enumerate(linhas):
        s.append(f'<text x="{x + 12:.0f}" y="{y + 48 + i * 18}" font-size="12" fill="#374151">{l}</text>')
    return s


def seta(x1, y1, x2, y2, cor):
    return [f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{cor}" stroke-width="1.5" marker-end="url(#ponta)"/>']


def montar() -> str:
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {L} {A}" width="{L}" height="{A}" '
         'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">',
         '<defs><marker id="ponta" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">'
         '<path d="M0,0 L9,4.5 L0,9 z" fill="#6b7280"/></marker></defs>',
         f'<rect width="{L}" height="{A}" fill="#ffffff"/>',
         f'<text x="{MARGEM}" y="32" font-size="18" font-weight="700" fill="#111827">Íris – Base de conhecimento e protótipo de RAG</text>']
    for titulo, tipo, y, caixas in FAIXAS:
        s.append(f'<text x="{MARGEM}" y="{y - 10}" font-size="12" font-weight="700" fill="{COR[tipo][0]}" letter-spacing="0.5">{titulo}</text>')
        for i, (t, linhas) in enumerate(caixas):
            x = MARGEM + i * (LARG + VAO)
            s += caixa(x, y, LARG, ALT, t, linhas, tipo)
            if i:                                          # seta entre caixas consecutivas
                s += seta(x - VAO + 2, y + ALT / 2, x - 3, y + ALT / 2, "#6b7280")
    # ligação entre o banco vetorial (ingestão) e a busca vetorial (consulta)
    xb = MARGEM + 5 * (LARG + VAO) + LARG / 2
    xc = MARGEM + 2 * (LARG + VAO) + LARG / 2
    ym = 70 + ALT + 44
    s.append(f'<path d="M{xb:.0f},{70 + ALT} L{xb:.0f},{ym} L{xc:.0f},{ym} L{xc:.0f},{290 - 4}" fill="none" stroke="#6b7280" '
             'stroke-width="1.5" stroke-dasharray="5 4" marker-end="url(#ponta)"/>')
    s.append(f'<text x="{(xb + xc) / 2:.0f}" y="{ym - 7}" font-size="11" fill="#6b7280" text-anchor="middle">vetores gravados na ingestão</text>')
    titulo, y, caixas = MEDIDA
    s.append(f'<text x="{MARGEM}" y="{y - 10}" font-size="12" font-weight="700" fill="{COR["medida"][0]}" letter-spacing="0.5">{titulo}</text>')
    larg3 = (L - 2 * MARGEM - 2 * VAO) / 3
    for i, (t, linhas) in enumerate(caixas):
        s += caixa(MARGEM + i * (larg3 + VAO), y, larg3, 92, t, linhas, "medida")
    s.append("</svg>")
    return "\n".join(s) + "\n"


if __name__ == "__main__":
    destino = Path(__file__).resolve().parents[1] / "diagrama_arquitetura.svg"
    destino.write_text(montar(), encoding="utf-8")
    print("ok", destino.name)
