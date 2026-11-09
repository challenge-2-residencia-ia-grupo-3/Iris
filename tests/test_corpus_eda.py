import json

import pandas as pd
import pytest

from iris.eval import corpus_eda as eda


def _chunks():
    return pd.DataFrame(
        [
            {"chunk_id": "D1#0", "doc_id": "D1", "titulo": "T1", "secao": "S1", "idioma": "pt-BR",
             "parte": "A", "barreiras": ["memoria_trabalho"], "texto": "o aluno precisa de apoio " * 10},
            {"chunk_id": "D1#1", "doc_id": "D1", "titulo": "T1", "secao": "S1", "idioma": "pt-BR",
             "parte": "A", "barreiras": ["memoria_trabalho", "atencao"], "texto": "organizar as etapas " * 5},
            {"chunk_id": "D2#0", "doc_id": "D2", "titulo": "T2", "secao": "S2", "idioma": "en",
             "parte": "B", "barreiras": ["atencao"], "texto": "short clear instructions " * 8},
        ]
    )


def test_add_tokens_columns():
    df, _ = eda.add_tokens(_chunks())
    assert {"n_palavras", "tokens_texto", "tokens"} <= set(df.columns)
    assert (df["tokens"] >= df["tokens_texto"]).all()  # o prefixo só acrescenta tokens


def test_text_column_missing():
    with pytest.raises(KeyError):
        eda.text_column(pd.DataFrame({"x": [1]}))


def test_section_table_groups_doc_and_section():
    df, _ = eda.add_tokens(_chunks())
    sec = eda.section_table(df)
    assert len(sec) == 2
    assert sec.loc[sec["doc_id"] == "D1", "n_trechos"].iloc[0] == 2


def test_embedding_limits(tmp_path):
    f = tmp_path / "embeddings.py"
    f.write_text('MODELOS_DENSOS = {"a": {"nome": "x", "max_tokens": 512}, "b": {"nome": "y", "max_tokens": 1024}}\n')
    assert eda.embedding_limits(f) == {"a": 512, "b": 1024}
    assert eda.embedding_limits(tmp_path / "nao_existe.py") == {}


def test_chunk_size_report_flags_overflow():
    df, _ = eda.add_tokens(_chunks())
    rep = eda.chunk_size_report(df, max_tokens=10)
    assert rep["trechos_acima_do_limite"] == len(df)
    assert rep["max_palavras_sugerido"] >= 0


def test_barrier_balance_and_vocabulary(tmp_path):
    cat = {"caracteristicas": [
        {"id_caracteristica": "c1", "nome": "C1", "barreira_rag_associada": "memoria_trabalho"},
        {"id_caracteristica": "c2", "nome": "C2", "barreira_rag_associada": ["atencao"]},
        {"id_caracteristica": "c3", "nome": "C3", "barreira_rag_associada": "inexistente"},
    ]}
    p = tmp_path / "cat.json"
    p.write_text(json.dumps(cat), encoding="utf-8")
    catalog = eda.load_catalog(p)
    bal = eda.barrier_balance(_chunks(), catalog).set_index("id_caracteristica")
    assert bal.loc["c1", "n_trechos"] == 2
    assert bal.loc["c2", "n_trechos"] == 2
    assert bal.loc["c3", "n_trechos"] == 0
    assert eda.vocabulary_mismatch(_chunks(), catalog)["so_no_catalogo"] == ["inexistente"]


def _chunks_com_vazio():
    df = _chunks()
    vazio = {"chunk_id": "D3#0", "doc_id": "D3", "titulo": "T3", "secao": "S3", "idioma": "pt-BR",
             "parte": "C", "barreiras": ["atencao"], "n_palavras": 0, "texto": ""}
    return pd.concat([df, pd.DataFrame([vazio])], ignore_index=True)


def test_drop_empty():
    df, n = eda.drop_empty(_chunks_com_vazio())
    assert n == 1
    assert "D3#0" not in set(df["chunk_id"])
    assert len(df) == 3


def test_overflow_table_by_language():
    df, _ = eda.add_tokens(_chunks())
    t = eda.overflow_table(df, max_tokens=1, by="idioma").set_index("idioma")
    assert t.loc["pt-BR", "n_trechos"] == 2
    assert t.loc["pt-BR", "pct_acima"] == 100.0
    t0 = eda.overflow_table(df, max_tokens=10**6, by="idioma").set_index("idioma")
    assert (t0["acima"] == 0).all()


def test_max_words_by_language_portuguese_is_stricter():
    pt = "informações educacionais complementares extraordinárias " * 20
    en = "the cat sat on the mat and ate " * 20
    df = pd.DataFrame([
        {"chunk_id": "a", "doc_id": "a", "idioma": "pt-BR", "secao": "s", "texto": pt},
        {"chunk_id": "b", "doc_id": "b", "idioma": "en", "secao": "s", "texto": en},
    ])
    df, _ = eda.add_tokens(df)
    lim = eda.max_words_by_language(df, max_tokens=512)
    assert lim["pt-BR"] < lim["en"]


def test_embedding_models_keeps_name(tmp_path):
    f = tmp_path / "embeddings.py"
    f.write_text('MODELOS_DENSOS = {"a": {"nome": "org/modelo-a", "max_tokens": 512}}\n')
    assert eda.embedding_models(f)["a"]["nome"] == "org/modelo-a"
