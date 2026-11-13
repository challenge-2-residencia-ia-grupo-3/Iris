"""rodar_no_pc.py: gera A, C e D com o Llama 3.1 8B local (Ollama), no PC, com os mesmos prompts da VPS.

Não refaz a busca: usa saidas/prompts_ac.jsonl (prompts de A e C já montados, byte a byte iguais aos que o
Qwen recebeu) e saidas/trechos_busca.jsonl. Não precisa de modelo de embedding, reranker nem PyTorch.
O D roda o arnês da bancada com o código do grupo (clone em IRIS_GRUPO) e o chunks.jsonl do pacote.

Uso (PowerShell, dentro de semana3; ver RODAR-NO-PC.md):
    .venv\\Scripts\\python.exe rodar_no_pc.py conferir
    .venv\\Scripts\\python.exe rodar_no_pc.py teste        (2 perguntas de A e C e 2 questões do D)
    .venv\\Scripts\\python.exe rodar_no_pc.py ac           (A e C: 40 perguntas x 3 repetições = 240 respostas)
    .venv\\Scripts\\python.exe rodar_no_pc.py d            (D: 30 questões x 2 configurações x 3 rodadas)
    .venv\\Scripts\\python.exe rodar_no_pc.py tudo
Se parar no meio, rodar o mesmo comando de novo: continua de onde parou.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import comum as C

# segundo argumento escolhe o modelo: llama3.1-8b (padrão, produção) ou gpt-oss-20b
MODELO = sys.argv[2] if len(sys.argv) > 2 else "llama3.1-8b"
if MODELO not in C.MODELOS or C.MODELOS[MODELO][0] != "ollama":
    raise SystemExit(f"modelo desconhecido: {MODELO}. Use llama3.1-8b ou gpt-oss-20b")
ID_OLLAMA = C.MODELOS[MODELO][1]


def conferir() -> bool:
    ok = True
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        tags = json.loads(urllib.request.urlopen(url + "/api/tags", timeout=5).read())
        nomes = [m["name"] for m in tags.get("models", [])]
        if ID_OLLAMA in nomes:
            print(f"ok   Ollama no ar e {ID_OLLAMA} instalado")
        else:
            print(f"FALTA o modelo {ID_OLLAMA} no Ollama (instalados: {nomes}). Rodar: ollama pull {ID_OLLAMA}")
            ok = False
    except OSError as e:
        print(f"FALTA Ollama no ar em {url} ({e}). Abrir o Ollama pelo menu Iniciar.")
        ok = False
    for arq, n in ((C.PROMPTS_AC, 40), (C.TRECHOS_BUSCA, 40)):
        linhas = C.ler_jsonl(arq)
        print(("ok  " if len(linhas) == n else "FALTA") + f" {arq.name}: {len(linhas)} linhas (esperado {n})")
        ok &= len(linhas) == n
    grupo = os.environ.get("IRIS_GRUPO")
    if grupo and os.path.isdir(os.path.join(grupo, "backend", "src", "iris")):
        print(f"ok   código do grupo em {grupo}")
    else:
        print("FALTA a variável IRIS_GRUPO com o caminho do clone do grupo (só o D precisa)")
        ok = False
    chunks = C.PACOTE / "chunks.jsonl"
    print(("ok  " if chunks.exists() else "FALTA") + f" {chunks} (só o D precisa)")
    ok &= chunks.exists()
    try:
        import pydantic  # noqa: F401
        import rank_bm25  # noqa: F401
        print("ok   pacotes do D instalados")
    except ImportError as e:
        print(f"FALTA pacote do D: {e.name}. Rodar o passo de instalação do RODAR-NO-PC.md")
        ok = False
    print("tudo certo" if ok else "corrigir o que está como FALTA antes de rodar")
    return ok


def rodar_ac(limite: int | None = None) -> None:
    import gerar_ac
    argv = ["--modelo", MODELO, "--testes", "A,C"]
    if limite:
        argv += ["--limite", str(limite), "--repeticoes", "1"]
    gerar_ac.main(argv)


def rodar_d(limite: int | None = None) -> None:
    import teste_d
    argv = ["--provedor", "ollama", "--modelo", ID_OLLAMA, "--rodadas", "1" if limite else "3"]
    if limite:
        argv += ["--limite", str(limite)]
    teste_d.main(argv)


def rodar_qwen_resto() -> None:
    import qwen_resto
    qwen_resto.main()


def main() -> None:
    sys.dont_write_bytecode = True
    os.environ.setdefault("PYTHONUTF8", "1")
    acao = sys.argv[1] if len(sys.argv) > 1 else "conferir"
    if acao == "conferir":
        conferir()
    elif acao == "teste":
        rodar_ac(2)
        rodar_d(2)
        print("teste ok. Apagar as saídas do teste antes de rodar de verdade? Não precisa: a rodada de verdade "
              "continua a partir delas (são as mesmas perguntas, mesma repetição).")
    elif acao == "ac":
        rodar_ac()
    elif acao == "d":
        rodar_d()
    elif acao == "tudo":
        rodar_ac()
        rodar_d()
    elif acao == "qwen-resto":
        rodar_qwen_resto()
    else:
        raise SystemExit("ação desconhecida: use conferir, teste, ac, d, tudo ou qwen-resto")
    if acao != "conferir":
        print("pronto. Mandar para a Ana a pasta semana3\\saidas inteira (zipada).")


if __name__ == "__main__":
    main()
