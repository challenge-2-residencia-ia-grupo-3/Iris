"""Avaliação do juiz do Agente Auditor contra minutas rotuladas (História 2.1.4, #19).

Mede, para o juiz LLM em uso, se ele: (a) devolve JSON válido; (b) detecta resolução indevida;
(c) detecta intrusão (adaptação de característica NÃO selecionada) sem acusar minutas limpas.

    python -m iris.eval.juiz_auditor [caminho.json] [--provider ollama|groq] [--model M]

O conjunto `data/benchmarks/juiz_auditor_v1.json` é pequeno (18 minutas sintéticas, 5 questões)
e serve como termômetro, não como prova estatística.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from iris.agents.auditor import AgenteAuditor, caracteristicas_nao_selecionadas

CAMINHO_PADRAO = Path(__file__).resolve().parents[4] / "data" / "benchmarks" / "juiz_auditor_v1.json"


def carregar_casos(caminho: str | Path | None = None) -> list[dict[str, Any]]:
    casos = json.loads(Path(caminho or CAMINHO_PADRAO).read_text(encoding="utf-8"))
    obrig = {"id", "original", "travas", "selecionadas", "adaptada", "esperado_resolucao", "esperado_intrusoes"}
    for c in casos:
        faltam = obrig - set(c)
        if faltam:
            raise ValueError(f"Caso {c.get('id')} sem campos: {sorted(faltam)}")
    ids = [c["id"] for c in casos]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de caso repetidos")
    return casos


def _razao(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def avaliar_juiz(
    casos: Sequence[Mapping[str, Any]],
    auditor: AgenteAuditor,
    catalogos: Mapping[str, Any] | None = None,
    progresso: Callable[[int, int, str, float], None] | None = None,
) -> dict[str, Any]:
    tp = fp = fn = tn = 0  # resolução indevida
    i_tp = i_fp = i_fn = 0  # intrusão, por id de característica
    c_tp = c_fp = c_fn = c_tn = 0  # intrusão, por minuta (há ou não há)
    invalidos, erros, latencias = 0, [], []
    for k, c in enumerate(casos, 1):
        nao_sel = caracteristicas_nao_selecionadas(c["selecionadas"], catalogos)
        t0 = time.perf_counter()
        r = auditor.auditar(c["original"], c["adaptada"], c["travas"], nao_sel)
        latencias.append(time.perf_counter() - t0)
        if progresso:
            progresso(k, len(casos), c["id"], latencias[-1])
        invalidos += not r.juiz_valido
        esp_r, prev_r = bool(c["esperado_resolucao"]), r.resolucao_indevida
        tp += esp_r and prev_r
        fp += (not esp_r) and prev_r
        fn += esp_r and not prev_r
        tn += (not esp_r) and not prev_r
        esp_i, prev_i = set(c["esperado_intrusoes"]), set(r.intrusoes)
        i_tp += len(esp_i & prev_i)
        i_fp += len(prev_i - esp_i)
        i_fn += len(esp_i - prev_i)
        c_tp += bool(esp_i) and bool(prev_i)
        c_fp += (not esp_i) and bool(prev_i)
        c_fn += bool(esp_i) and not prev_i
        c_tn += (not esp_i) and not prev_i
        if not r.juiz_valido or esp_r != prev_r or esp_i != prev_i:
            erros.append({"id": c["id"], "juiz_valido": r.juiz_valido, "esperado_resolucao": esp_r,
                          "previsto_resolucao": prev_r, "esperado_intrusoes": sorted(esp_i),
                          "previstas_intrusoes": sorted(prev_i)})
    n = len(casos)
    return {
        "n_casos": n,
        "json_invalido": invalidos,
        "resolucao": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                      "precisao": _razao(tp, tp + fp), "recall": _razao(tp, tp + fn),
                      "acuracia": _razao(tp + tn, n)},
        "intrusao_por_minuta": {"tp": c_tp, "fp": c_fp, "fn": c_fn, "tn": c_tn,
                                "precisao": _razao(c_tp, c_tp + c_fp), "recall": _razao(c_tp, c_tp + c_fn),
                                "acuracia": _razao(c_tp + c_tn, n)},
        "intrusao_por_id": {"tp": i_tp, "fp": i_fp, "fn": i_fn,
                            "precisao": _razao(i_tp, i_tp + i_fp), "recall": _razao(i_tp, i_tp + i_fn)},
        "latencia_media_s": round(sum(latencias) / n, 2) if n else None,
        "erros": erros,
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    from iris.core.llm_client import get_llm_client

    ap = argparse.ArgumentParser(description="Mede a precisão do juiz do Agente Auditor.")
    ap.add_argument("caminho", nargs="?", default=None)
    ap.add_argument("--provider", default=None, help="ollama | groq (padrão: IRIS_LLM_PROVIDER)")
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)

    import sys

    def mostrar(k: int, n: int, cid: str, seg: float) -> None:
        print(f"[{k}/{n}] {cid} ({seg:.1f}s)", file=sys.stderr, flush=True)

    cliente = get_llm_client(provider=args.provider, model=args.model)
    print("Avaliando... (cada minuta chama o modelo; no Ollama local pode levar minutos)", file=sys.stderr, flush=True)
    rel = avaliar_juiz(carregar_casos(args.caminho), AgenteAuditor(cliente), progresso=mostrar)
    erros = rel.pop("erros")
    print(f"Juiz: {cliente.provider_name}" + (f" / {args.model}" if args.model else ""))
    print(json.dumps(rel, ensure_ascii=False, indent=2))
    print(f"\n{len(erros)} minuta(s) com divergência:")
    for e in erros:
        print(" -", json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()