"""EDA 1: corpus científico do RAG (Épico 4.2, #38).

Analisa os trechos (chunks) que o `ingestao.py` do time de RAG gera, sem refazer o
corte: lê `rag/iris-rag/pacote/chunks.jsonl` e produz

  1. histograma de tokens por trecho e por seção (fundamenta o `chunk_size`);
  2. balanceamento do corpus por característica atômica do catálogo TDAH.

Uso:
    uv run python -m iris.eval.corpus_eda            # gera tabelas e gráficos em reports/
    uv run python -m iris.eval.corpus_eda --max-tokens 512

Se `chunks.jsonl` não existir (ele não é versionado), gere-o antes:
    cd rag/iris-rag/pacote && python ingestao.py
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------- caminhos

CHUNKS_REL = Path("rag/iris-rag/pacote/chunks.jsonl")
CATALOG_REL = Path("rag/catalogs/tdah_caracteristicas_funcionais.json")
EMBEDDINGS_REL = Path("rag/iris-rag/pacote/embeddings.py")

TEXT_COLUMNS = ("texto_indexado", "texto", "conteudo", "text")


def find_root(start: Path | None = None) -> Path:
    """Sobe a partir de `start` até achar a pasta com pyproject.toml."""
    start = (start or Path.cwd()).resolve()
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
    raise FileNotFoundError("pyproject.toml não encontrado: rode a partir da pasta do projeto.")


# ---------------------------------------------------------------- tokens


def get_token_counter(encoding: str = "cl100k_base"):
    """Devolve (função de contagem, descrição do método).

    Usa `tiktoken`. Se o vocabulário não puder ser carregado (sem rede), cai numa
    aproximação e AVISA: os números passam a ser estimativas.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding(encoding)
        return (lambda s: len(enc.encode(s, disallowed_special=())), f"tiktoken/{encoding}")
    except Exception as exc:  # noqa: BLE001 - qualquer falha de rede/vocabulário
        warnings.warn(
            f"tiktoken indisponível ({type(exc).__name__}); usando contagem APROXIMADA de tokens.",
            stacklevel=2,
        )
        word_re = re.compile(r"\w+|[^\w\s]", re.UNICODE)
        return (
            lambda s: sum(1 if len(w) <= 4 else math.ceil(len(w) / 4) for w in word_re.findall(s)),
            "aproximação (palavras/4 caracteres)",
        )


# ---------------------------------------------------------------- carga


def load_chunks(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} não existe (arquivo não versionado). Gere com: "
            "cd rag/iris-rag/pacote && python ingestao.py"
        )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"{path} está vazio.")
    return pd.DataFrame(rows)


def text_column(df: pd.DataFrame) -> str:
    for col in TEXT_COLUMNS:
        if col in df.columns:
            return col
    raise KeyError(f"Nenhuma coluna de texto entre {TEXT_COLUMNS}. Colunas do arquivo: {list(df.columns)}")


def drop_empty(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove trechos vazios (ex.: placeholders de documentos sem texto distribuído).

    Devolve (df sem vazios, quantos foram removidos).
    """
    col = text_column(df)
    empty = df[col].astype(str).str.strip().eq("")
    if "n_palavras" in df.columns:
        empty |= df["n_palavras"].eq(0)  # NaN = desconhecido, não vazio
    return df.loc[~empty].reset_index(drop=True), int(empty.sum())


def indexed_text(row: pd.Series, col: str) -> str:
    """Texto como vai para o modelo: 'Documento: <titulo> | Seção: <secao>' + trecho."""
    body = str(row[col])
    if body.startswith("Documento:"):
        return body
    return f"Documento: {row.get('titulo', '')} | Seção: {row.get('secao', '')}\n{body}"


def get_model_token_counter(model_name: str):
    """Contador com o tokenizador REAL do modelo de embeddings (precisa de `transformers` e internet)."""
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("`transformers` não instalado. Rode: uv add transformers") from exc
    tok = AutoTokenizer.from_pretrained(model_name)
    tok.model_max_length = 10**9  # só contamos; sem o aviso de "sequência longa demais"
    return (lambda s: len(tok.encode(s, add_special_tokens=True, truncation=False)), f"tokenizador/{model_name}")


def add_tokens(
    df: pd.DataFrame, encoding: str = "cl100k_base", tokenizer_model: str | None = None
) -> tuple[pd.DataFrame, str]:
    """Acrescenta `n_palavras`, `tokens_texto` (só o trecho) e `tokens` (texto indexado).

    Com `tokenizer_model`, usa o tokenizador do modelo; senão, `tiktoken` (proxy).
    """
    count, method = get_model_token_counter(tokenizer_model) if tokenizer_model else get_token_counter(encoding)
    col = text_column(df)
    out = df.copy()
    body = out[col].astype(str)
    if "n_palavras" not in out.columns:
        out["n_palavras"] = body.str.split().str.len()
    out["tokens_texto"] = body.map(count)
    out["tokens"] = out.apply(lambda r: count(indexed_text(r, col)), axis=1)
    if "secao" not in out.columns:
        out["secao"] = "(sem seção)"
    return out, method


# ---------------------------------------------------------------- limite do modelo


def embedding_models(embeddings_py: str | Path) -> dict[str, dict]:
    """Lê `MODELOS_DENSOS` de embeddings.py (sem importar): {apelido: {nome, max_tokens, ...}}."""
    path = Path(embeddings_py)
    if not path.exists():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MODELOS_DENSOS" for t in node.targets
            ):
                return {k: dict(v) for k, v in ast.literal_eval(node.value).items()}
    except (SyntaxError, ValueError, TypeError):
        pass
    return {}


def embedding_limits(embeddings_py: str | Path) -> dict[str, int]:
    """{apelido: max_tokens} de cada modelo denso."""
    return {k: int(v["max_tokens"]) for k, v in embedding_models(embeddings_py).items() if "max_tokens" in v}


# ---------------------------------------------------------------- estatísticas


def token_percentiles(s: pd.Series) -> dict[str, float]:
    q = s.quantile([0.5, 0.75, 0.9, 0.95, 0.99])
    return {
        "n": int(s.size),
        "min": int(s.min()),
        "p50": int(q[0.5]),
        "p75": int(q[0.75]),
        "p90": int(q[0.9]),
        "p95": int(q[0.95]),
        "p99": int(q[0.99]),
        "max": int(s.max()),
        "media": round(float(s.mean()), 1),
    }


def section_table(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (documento, seção): nº de trechos e tokens somados.

    A soma inclui a sobreposição entre trechos vizinhos, então é um limite superior
    do tamanho real da seção.
    """
    g = df.groupby(["doc_id", "secao"], sort=False)
    return g.agg(n_trechos=("chunk_id", "count"), tokens=("tokens_texto", "sum")).reset_index()


def tokens_per_word(df: pd.DataFrame) -> pd.Series:
    """Razão tokens/palavra por idioma (PT-BR tende a gastar mais tokens que EN)."""
    key = "idioma" if "idioma" in df.columns else None
    if key is None:
        return pd.Series({"todos": df["tokens_texto"].sum() / df["n_palavras"].sum()})
    g = df.groupby(key)
    return (g["tokens_texto"].sum() / g["n_palavras"].sum()).round(2)


def overflow_table(df: pd.DataFrame, max_tokens: int, by: str = "idioma") -> pd.DataFrame:
    """Trechos acima do limite de tokens, agrupados por `by` (idioma, doc_id, parte...)."""
    g = df.assign(acima=df["tokens"] > max_tokens).groupby(by)
    out = g.agg(
        n_trechos=("chunk_id", "count"),
        acima=("acima", "sum"),
        tokens_p90=("tokens", lambda s: int(s.quantile(0.9))),
    ).reset_index()
    out["pct_acima"] = (100 * out["acima"] / out["n_trechos"]).round(1)
    return out.sort_values(["pct_acima", "acima"], ascending=False).reset_index(drop=True)


def max_words_by_language(df: pd.DataFrame, max_tokens: int, margin: float = 0.9) -> dict[str, int]:
    """Máximo de palavras por trecho em cada idioma para o trecho TÍPICO caber no limite.

    Usa a razão média tokens/palavra do idioma e deixa `1 - margin` de folga para o prefixo.
    Trechos com razão acima da média ainda podem passar do limite.
    """
    g = df.groupby("idioma")
    ratio = g["tokens_texto"].sum() / g["n_palavras"].sum()
    return {str(k): int(margin * max_tokens / v) for k, v in ratio.items()}


def chunk_size_report(df: pd.DataFrame, max_tokens: int | None, max_palavras: int = 350) -> dict:
    """Resumo quantitativo para fundamentar o chunk_size, em tokens e em palavras."""
    rep: dict = {
        "tokens_por_trecho": token_percentiles(df["tokens"]),
        "palavras_por_trecho": token_percentiles(df["n_palavras"]),
        "tokens_por_palavra": float(df["tokens_texto"].sum() / df["n_palavras"].sum()),
        "tokens_por_palavra_por_idioma": tokens_per_word(df).to_dict(),
        "max_palavras_atual": max_palavras,
        "acima_do_max_palavras": int((df["n_palavras"] > max_palavras).sum()),
    }
    if max_tokens:
        over = df["tokens"] > max_tokens
        ratio = rep["tokens_por_palavra"]
        rep.update(
            {
                "limite_modelo_tokens": max_tokens,
                "trechos_acima_do_limite": int(over.sum()),
                "pct_acima_do_limite": round(100 * float(over.mean()), 1),
                # palavras que cabem no limite, com folga de 10% para o prefixo de contexto
                "max_palavras_sugerido": int(0.9 * max_tokens / ratio),
            }
        )
        if "idioma" in df.columns:
            rep["max_palavras_sugerido_por_idioma"] = max_words_by_language(df, max_tokens)
            rep["estouro_por_idioma"] = json.loads(overflow_table(df, max_tokens, "idioma").to_json(orient="records"))
    return rep


# ---------------------------------------------------------------- catálogo e balanceamento


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def load_catalog(path: str | Path) -> pd.DataFrame:
    """Características atômicas: id, nome e barreira(s) do RAG associada(s)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for c in data["caracteristicas"]:
        key = next((k for k in c if k.startswith("barreira")), None)
        rows.append(
            {
                "id_caracteristica": c["id_caracteristica"],
                "nome": c.get("nome", c["id_caracteristica"]),
                "barreiras": _as_list(c.get(key)) if key else [],
            }
        )
    return pd.DataFrame(rows)


def barrier_balance(chunks: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Trechos que cobrem cada característica (via a barreira do RAG associada).

    Um trecho pode ter várias barreiras, então as contagens se sobrepõem.
    """
    if "barreiras" not in chunks.columns:
        raise KeyError("chunks.jsonl não tem a coluna 'barreiras'.")
    per_barrier = chunks.explode("barreiras").groupby("barreiras")["chunk_id"].nunique()
    rows = []
    for _, c in catalog.iterrows():
        ids = set()
        for b in c["barreiras"]:
            ids |= set(chunks.loc[chunks["barreiras"].map(lambda x, b=b: b in _as_list(x)), "chunk_id"])
        rows.append(
            {
                "id_caracteristica": c["id_caracteristica"],
                "nome": c["nome"],
                "barreiras": ", ".join(c["barreiras"]) or "(sem barreira no catálogo)",
                "n_trechos": len(ids),
                "n_docs": chunks.loc[chunks["chunk_id"].isin(ids), "doc_id"].nunique(),
            }
        )
    out = pd.DataFrame(rows).sort_values("n_trechos", ascending=False).reset_index(drop=True)
    out.attrs["vocabulario_chunks"] = sorted(per_barrier.index.astype(str))
    return out


def vocabulary_mismatch(chunks: pd.DataFrame, catalog: pd.DataFrame) -> dict[str, list[str]]:
    """Barreiras do catálogo sem nenhum trecho, e barreiras dos trechos fora do catálogo."""
    in_chunks = set(chunks.explode("barreiras")["barreiras"].dropna().astype(str))
    in_catalog = {b for bs in catalog["barreiras"] for b in bs}
    return {
        "so_no_catalogo": sorted(in_catalog - in_chunks),
        "so_nos_trechos": sorted(in_chunks - in_catalog),
    }


# ---------------------------------------------------------------- gráficos

_COLORS = {"azul": "#4C78A8", "laranja": "#F58518", "vermelho": "#E45756", "verde": "#54A24B"}


def _style() -> None:
    plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})


def plot_chunk_tokens(df: pd.DataFrame, max_tokens: int | None, out: Path | None = None):
    _style()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(df["tokens"], bins=40, color=_COLORS["azul"], edgecolor="white")
    p = token_percentiles(df["tokens"])
    for name, color in (("p50", "verde"), ("p90", "laranja")):
        ax.axvline(p[name], color=_COLORS[color], ls="--", label=f"{name} = {p[name]}")
    if max_tokens:
        ax.axvline(max_tokens, color=_COLORS["vermelho"], lw=2, label=f"limite do modelo = {max_tokens}")
    ax.set(title="Tokens por trecho (texto indexado)", xlabel="tokens", ylabel="nº de trechos")
    ax.legend()
    fig.tight_layout()
    if out:
        fig.savefig(out)
    return fig


def plot_section_tokens(sections: pd.DataFrame, out: Path | None = None):
    _style()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(sections["tokens"], bins=40, color=_COLORS["laranja"], edgecolor="white")
    med = sections["tokens"].median()
    ax.axvline(med, color=_COLORS["vermelho"], ls="--", label=f"mediana = {int(med)}")
    ax.set(
        title="Tokens por seção (documento + seção)",
        xlabel="tokens da seção (com sobreposição)",
        ylabel="nº de seções",
    )
    ax.legend()
    fig.tight_layout()
    if out:
        fig.savefig(out)
    return fig


def plot_tokens_by_doc(df: pd.DataFrame, out: Path | None = None):
    _style()
    order = df.groupby("doc_id")["tokens"].median().sort_values().index
    fig, ax = plt.subplots(figsize=(8, max(3, 0.28 * len(order))))
    ax.boxplot([df.loc[df["doc_id"] == d, "tokens"] for d in order], orientation="horizontal", tick_labels=order)
    ax.set(title="Tokens por trecho, por documento", xlabel="tokens")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    if out:
        fig.savefig(out)
    return fig


def plot_overflow_by_doc(df: pd.DataFrame, max_tokens: int, out: Path | None = None):
    _style()
    t = overflow_table(df, max_tokens, "doc_id").sort_values("pct_acima")
    fig, ax = plt.subplots(figsize=(8, max(3, 0.28 * len(t))))
    bars = ax.barh(t["doc_id"], t["pct_acima"], color=_COLORS["vermelho"])
    ax.bar_label(bars, labels=[f"{int(a)}/{int(n)}" for a, n in zip(t["acima"], t["n_trechos"])], padding=3, fontsize=7)
    ax.set(title=f"% de trechos acima de {max_tokens} tokens, por documento", xlabel="% dos trechos do documento")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    if out:
        fig.savefig(out)
    return fig


def plot_balance(balance: pd.DataFrame, out: Path | None = None):
    _style()
    d = balance.sort_values("n_trechos")
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * len(d))))
    colors = [_COLORS["vermelho"] if n == 0 else _COLORS["azul"] for n in d["n_trechos"]]
    bars = ax.barh(d["nome"].str.slice(0, 70), d["n_trechos"], color=colors)
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set(title="Trechos do corpus por característica atômica (via barreira do RAG)", xlabel="nº de trechos")
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    if out:
        fig.savefig(out)
    return fig


def plot_balance_by_part(df: pd.DataFrame, out: Path | None = None):
    _style()
    if "parte" not in df.columns:
        return None
    counts = df["parte"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(counts.index.astype(str), counts.values, color=_COLORS["azul"])
    ax.set(title="Trechos por parte do corpus (A=DUA, B=Funções Exec., C=Normas MEC, D=Pesquisa)", ylabel="nº de trechos")
    ax.title.set_fontsize(9)
    fig.tight_layout()
    if out:
        fig.savefig(out)
    return fig


# ---------------------------------------------------------------- execução


def run(
    root: Path | None = None,
    max_tokens: int | None = None,
    encoding: str = "cl100k_base",
    tokenizer: str | None = None,
) -> dict:
    """Roda a EDA completa e grava tabelas/figuras em reports/. Devolve o resumo.

    `tokenizer`: apelido de um modelo de embeddings.py (ex.: "mpnet") para usar o tokenizador
    real dele e o limite dele; sem isso, usa tiktoken e o menor limite entre os modelos.
    """
    root = root or find_root()
    reports = root / "reports"
    reports.mkdir(exist_ok=True)

    models = embedding_models(root / EMBEDDINGS_REL)
    limits = {k: int(v["max_tokens"]) for k, v in models.items() if "max_tokens" in v}
    tokenizer_model = None
    if tokenizer:
        if tokenizer not in models:
            raise KeyError(f"Modelo '{tokenizer}' não está em MODELOS_DENSOS: {list(models)}")
        tokenizer_model = models[tokenizer]["nome"]
        max_tokens = max_tokens or limits.get(tokenizer)

    raw, n_vazios = drop_empty(load_chunks(root / CHUNKS_REL))
    df, method = add_tokens(raw, encoding, tokenizer_model)
    if max_tokens is None and limits:
        max_tokens = min(limits.values())  # critério conservador: o menor limite entre os modelos

    sections = section_table(df)
    report = chunk_size_report(df, max_tokens)
    report["metodo_tokens"] = method
    report["trechos_vazios_excluidos"] = n_vazios
    report["limites_modelos"] = limits

    if max_tokens:
        overflow_table(df, max_tokens, "doc_id").to_csv(reports / "eda1_estouro_por_documento.csv", index=False)
        plot_overflow_by_doc(df, max_tokens, reports / "eda1_estouro_por_documento.png")
    plot_chunk_tokens(df, max_tokens, reports / "eda1_tokens_trecho.png")
    plot_section_tokens(sections, reports / "eda1_tokens_secao.png")
    plot_tokens_by_doc(df, reports / "eda1_tokens_documento.png")
    plot_balance_by_part(df, reports / "eda1_balanceamento_parte.png")

    catalog_path = root / CATALOG_REL
    if catalog_path.exists() and "barreiras" in df.columns:
        catalog = load_catalog(catalog_path)
        balance = barrier_balance(df, catalog)
        balance.to_csv(reports / "eda1_balanceamento_caracteristica.csv", index=False)
        plot_balance(balance, reports / "eda1_balanceamento_caracteristica.png")
        report["caracteristicas_sem_trechos"] = balance.loc[balance["n_trechos"] == 0, "id_caracteristica"].tolist()
        report["vocabulario"] = vocabulary_mismatch(df, catalog)

    sections.to_csv(reports / "eda1_secoes.csv", index=False)
    (reports / "eda1_resumo.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    plt.close("all")
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-tokens", type=int, default=None, help="limite de tokens do modelo (padrão: lido de embeddings.py)")
    ap.add_argument("--encoding", default="cl100k_base")
    ap.add_argument("--tokenizer", default=None, help="apelido do modelo (ex.: mpnet) para usar o tokenizador real")
    args = ap.parse_args(argv)
    result = run(max_tokens=args.max_tokens, encoding=args.encoding, tokenizer=args.tokenizer)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()