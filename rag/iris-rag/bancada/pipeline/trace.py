"""trace.py: ambiente, rastreador e provedores do arnês de ponta a ponta do Íris.

O arnês usa o código do grupo (clone em IRIS_GRUPO, só leitura) SEM alterar nenhum arquivo dele:
  * o código do grupo entra pelo sys.path (backend/src e rag/iris-rag/pacote);
  * nenhum .pyc é gravado no clone (sys.dont_write_bytecode);
  * cada função do grupo que interessa é envolvida por um wrapper em tempo de execução
    (monkeypatch do nome no módulo que a chama), que grava entrada, saída, latência e erro;
  * o chunks.jsonl do RAG vem do pacote congelado deste repositório (não é gerado dentro do clone).

Provedores de LLM aceitos:
  extractive  ExtractiveFallbackLLMProvider do grupo (determinístico; o Extrator e o Adaptador
              do grupo pulam o modelo e usam as regras de reserva)
  eco         stub deste arnês (determinístico, sem rede): responde JSON válido para o Extrator e o
              Adaptador, para exercitar o caminho "com modelo" (parse, laudo de escopo, telemetria)
  ollama      OllamaLLMProvider do grupo (só no PC; modelo padrão llama3:latest)
O provedor 'groq' (API externa) é recusado de propósito.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # não gravar __pycache__ dentro do clone do grupo

import hashlib
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------- caminhos
AQUI = Path(__file__).resolve().parent
IRIS_RAG = AQUI.parent.parent  # .../iris-rag
PACOTE = IRIS_RAG / "pacote"
OUTPUTS = PACOTE / "outputs"
REPORTS = PACOTE / "reports" / "pipeline"  # ignorado pelo git (pacote/reports/)

import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("onde", Path(__file__).resolve().parents[1] / "onde.py")
_onde = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_onde)
GRUPO_PADRAO = _onde.grupo()
GRUPO = Path(os.environ.get("IRIS_GRUPO", str(GRUPO_PADRAO))).expanduser().resolve()
CHUNKS = Path(os.environ.get("IRIS_BANCADA_CHUNKS", str(PACOTE / "chunks.jsonl"))).expanduser().resolve()
COMMIT_ESPERADO = "65e1f09"
MODELO_PADRAO_OLLAMA = "llama3:latest"
LIMITE_TEXTO_RASTRO = 20_000  # caracteres por campo no rastro completo

_PREPARADO = False


def preparar_ambiente() -> None:
    """Coloca o código do grupo no sys.path. Idempotente."""
    global _PREPARADO
    if _PREPARADO:
        return
    if not (GRUPO / "backend" / "src" / "iris").is_dir():
        raise SystemExit(
            f"Clone do grupo não encontrado em {GRUPO}. Defina IRIS_GRUPO com o caminho do clone (commit {COMMIT_ESPERADO})."
        )
    for p in (GRUPO / "backend" / "src", GRUPO / "rag" / "iris-rag" / "pacote"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    # o pacote deste repositório tem módulos com o mesmo nome (consultar, ingestao...): não pode estar no caminho
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != PACOTE]
    os.environ.setdefault("PYTHONUTF8", "1")
    _PREPARADO = True


def commit_grupo() -> str:
    try:
        r = subprocess.run(["git", "-C", str(GRUPO), "rev-parse", "--short=7", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "desconhecido"
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"


def sha16(caminho: Path) -> str:
    try:
        return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
    except OSError:
        return "ausente"


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def carimbo() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------- RAG sem tocar no clone
_RAG_PRONTO = False


def preparar_rag() -> dict:
    """Importa os módulos do RAG do grupo e faz o carregador de chunks ler o chunks.jsonl congelado.

    Sem isto, ``ingestao.carregar_chunks`` geraria o arquivo DENTRO do clone do grupo. Na VPS e no PC
    o arnês só usa o método 'bm25' (não carrega Qwen3, torch nem banco).
    """
    global _RAG_PRONTO
    preparar_ambiente()
    from iris.rag import bridge

    ingestao, consultar, _gerar = bridge.carregar_modulos_rag()
    if not _RAG_PRONTO:
        if not CHUNKS.exists():
            raise FileNotFoundError(f"chunks.jsonl não encontrado em {CHUNKS} (defina IRIS_BANCADA_CHUNKS)")
        cache: list[dict] = []

        def carregar_chunks_congelado(caminho: Any = None) -> list[dict]:
            if not cache:
                cache.extend(json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x)
            return cache

        ingestao.carregar_chunks = carregar_chunks_congelado
        consultar._base.cache_clear()
        _RAG_PRONTO = True
    return {"chunks": str(CHUNKS), "sha16": sha16(CHUNKS), "metodo": "bm25"}


# ---------------------------------------------------------------- serialização
def serializar(obj: Any, limite: int = LIMITE_TEXTO_RASTRO) -> Any:
    """Transforma objetos do grupo (pydantic, dataclass, exceções) em JSON, truncando textos longos."""
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= limite else obj[:limite] + f"... [truncado, {len(obj)} caracteres]"
    if isinstance(obj, bytes):
        return f"<{len(obj)} bytes sha256={hashlib.sha256(obj).hexdigest()[:16]}>"
    if isinstance(obj, BaseException):
        return {"tipo": type(obj).__name__, "codigo": getattr(obj, "code", None), "mensagem": str(obj)[:500]}
    if hasattr(obj, "model_dump"):
        try:
            return serializar(obj.model_dump(), limite)
        except Exception:  # noqa: BLE001
            pass
    if is_dataclass(obj) and not isinstance(obj, type):
        return serializar(asdict(obj), limite)
    if isinstance(obj, dict):
        return {str(k): serializar(v, limite) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [serializar(v, limite) for v in obj]
    return serializar(str(obj), limite)


def tamanho(obj: Any) -> int:
    """Tamanho em caracteres da representação JSON (comparável entre etapas)."""
    if obj is None:
        return 0
    if isinstance(obj, str):
        return len(obj)
    try:
        return len(json.dumps(serializar(obj), ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(obj))


# ---------------------------------------------------------------- rastreador
class Rastreador:
    """Grava uma linha por etapa no esquema da bancada."""

    def __init__(self, run_id: str, material_id: str, provedor: str, modelo: str, commit: str) -> None:
        self.run_id = run_id
        self.material_id = material_id
        self.provedor = provedor
        self.modelo = modelo
        self.commit = commit
        self.linhas: list[dict] = []
        self._ordem = 0
        self._pilha: list[dict] = []
        self.questao: str | None = None

    # tokens das chamadas de LLM feitas durante a etapa aberta
    def somar_tokens(self, entrada: int, saida: int, modelo: str | None, provedor: str | None) -> None:
        for linha in self._pilha:
            linha["tokens_entrada"] += int(entrada or 0)
            linha["tokens_saida"] += int(saida or 0)
            if modelo:
                linha["modelo"] = modelo
            if provedor:
                linha["provedor"] = provedor

    def _nova(self, etapa: str, funcao: str, entrada: Any, status: str = "ok") -> dict:
        self._ordem += 1
        linha = {
            "run_id": self.run_id, "material_id": self.material_id, "ordem": self._ordem,
            "etapa": etapa, "funcao": funcao, "entrada": serializar(entrada), "saida": None,
            "latencia_s": 0.0, "tokens_entrada": 0, "tokens_saida": 0,
            "modelo": None, "provedor": None, "erro": None, "commit_grupo": self.commit,
            "status": status, "questao": self.questao, "tamanho_entrada": tamanho(entrada),
            "tamanho_saida": 0, "resumo_saida": "",
        }
        self.linhas.append(linha)
        return linha

    @contextmanager
    def etapa(self, etapa: str, funcao: str, entrada: Any, resumir: Callable[[Any], str] | None = None):
        """Uso: with r.etapa(...) as reg: reg['saida_obj'] = resultado."""
        linha = self._nova(etapa, funcao, entrada)
        self._pilha.append(linha)
        caixa: dict = {}
        t0 = time.perf_counter()
        try:
            yield caixa
        except Exception as exc:
            linha["status"] = "erro"
            linha["erro"] = serializar(exc)
            linha["resumo_saida"] = f"{type(exc).__name__}: {getattr(exc, 'code', '') or ''} {str(exc)[:150]}".strip()[:200]
            raise
        finally:
            linha["latencia_s"] = round(time.perf_counter() - t0, 4)
            self._pilha.remove(linha)
            if "saida" in caixa:
                linha["saida"] = serializar(caixa["saida"])
                linha["tamanho_saida"] = tamanho(caixa["saida"])
                if linha["status"] == "ok":
                    try:
                        linha["resumo_saida"] = (resumir(caixa["saida"]) if resumir else _resumo_padrao(caixa["saida"]))[:200]
                    except Exception as e:  # noqa: BLE001
                        linha["resumo_saida"] = f"(resumo indisponível: {type(e).__name__})"

    def nao_implementada(self, etapa: str, descricao: str) -> None:
        linha = self._nova(etapa, "nao_implementada", None, status="nao_implementada")
        linha["resumo_saida"] = f"não implementada no commit {commit_grupo()}: {descricao}"[:200]

    def envolver(self, modulo: Any, nome: str, etapa: str, resumir: Callable[[Any], str] | None = None,
                 entrada: Callable[..., Any] | None = None) -> Callable[[], None]:
        """Troca ``modulo.nome`` por um wrapper que registra a chamada; devolve a função que desfaz."""
        original = getattr(modulo, nome)
        rotulo = f"{modulo.__name__}:{getattr(original, '__qualname__', nome)}"
        rastreador = self

        def wrapper(*args, **kwargs):
            ent = entrada(*args, **kwargs) if entrada else {"args": args, "kwargs": kwargs}
            with rastreador.etapa(etapa, rotulo, ent, resumir) as caixa:
                resultado = original(*args, **kwargs)
                caixa["saida"] = resultado
            return resultado

        wrapper.__wrapped__ = original  # type: ignore[attr-defined]
        setattr(modulo, nome, wrapper)
        return lambda: setattr(modulo, nome, original)

    def gravar(self, pasta: Path = REPORTS) -> Path:
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{self.run_id}.jsonl"
        with destino.open("w", encoding="utf-8") as f:
            for linha in self.linhas:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        return destino

    def resumo(self) -> dict:
        return {
            "run_id": self.run_id,
            "material_id": self.material_id,
            "etapas": [
                {"ordem": l["ordem"], "etapa": l["etapa"], "funcao": l["funcao"], "questao": l["questao"],
                 "status": l["status"], "latencia_s": l["latencia_s"], "tamanho_entrada": l["tamanho_entrada"],
                 "tamanho_saida": l["tamanho_saida"], "tokens_entrada": l["tokens_entrada"],
                 "tokens_saida": l["tokens_saida"], "resumo_saida": l["resumo_saida"]}
                for l in self.linhas
            ],
        }


def _resumo_padrao(obj: Any) -> str:
    if isinstance(obj, str):
        return obj.replace("\n", " / ")
    if isinstance(obj, tuple):
        return " | ".join(_resumo_padrao(x) for x in obj)
    return type(obj).__name__


# ---------------------------------------------------------------- provedores
class ProvedorEco:
    """Stub determinístico (sem rede) que finge ser um modelo que obedece ao formato pedido.

    * Extrator: devolve o JSON dos invariantes calculados pela salvaguarda determinística do grupo.
    * Adaptador: devolve JSON com o andaime por regras do grupo (nível 1 negrito, níveis 2 e 3 etapas).
    * Qualquer outro prompt (diretiva do Estrategista): delega ao ExtractiveFallbackLLMProvider.
    Serve para exercitar o caminho "com modelo" do Extrator e do Adaptador (parse, laudo, telemetria).
    Não mede qualidade de modelo nenhum.
    """

    provider_name = "eco"

    def __init__(self) -> None:
        preparar_ambiente()
        from iris.core.llm_client import ExtractiveFallbackLLMProvider

        self.model = "eco-stub-deterministico"
        self._extrativo = ExtractiveFallbackLLMProvider()

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500,
                 system_prompt: str | None = None, json_mode: bool = False):
        from iris.core.llm_client import LLMResponse

        t0 = time.perf_counter()
        sistema = system_prompt or ""
        if "Agente Extrator Curricular" in sistema:
            from iris.agents.curriculum_extractor import CurriculumExtractorAgent
            from iris.schemas.curriculum import ExtractionRequest

            m = re.search(r"ENUNCIADO:\n(.*?)(?:\nTRAVAS DO PROFESSOR|\Z)", prompt, flags=re.DOTALL)
            enunciado = (m.group(1) if m else prompt).strip()
            inv = CurriculumExtractorAgent._extracao_deterministica_fallback(
                None, ExtractionRequest(enunciado=enunciado if len(enunciado) >= 15 else enunciado.ljust(15))  # type: ignore[arg-type]
            )
            texto = json.dumps(inv.model_dump(), ensure_ascii=False)
        elif "Agente Adaptador Pedagógico" in sistema:
            from iris.agents.adapter_agent import decompor_em_etapas, destacar_comandos

            m = re.search(r"ENUNCIADO ORIGINAL:\n(.*)\Z", prompt, flags=re.DOTALL)
            enunciado = (m.group(1) if m else "").strip()
            nivel = int((re.search(r"NÍVEL (\d)", prompt) or [None, "2"])[1])
            adaptado = destacar_comandos(enunciado) if nivel == 1 else decompor_em_etapas(enunciado, com_registro=nivel == 3)
            texto = json.dumps({"texto_adaptado": adaptado, "justificativas": ["eco: andaime por regras"]}, ensure_ascii=False)
        else:
            r = self._extrativo.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
            return LLMResponse(text=r.text, provider=self.provider_name, model=self.model,
                               prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens,
                               latency_ms=r.latency_ms, raw_usage=r.raw_usage)
        p, c = len((sistema + prompt).split()), len(texto.split())
        return LLMResponse(text=texto, provider=self.provider_name, model=self.model, prompt_tokens=p,
                           completion_tokens=c, latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                           raw_usage={"prompt_tokens": p, "completion_tokens": c})


class ClienteRastreado:
    """Repassa ao cliente real e soma tokens na etapa aberta do rastreador; guarda os prompts recebidos."""

    def __init__(self, cliente: Any, provedor: str) -> None:
        self.cliente = cliente
        self.provider_name = provedor
        self.rastreador: Rastreador | None = None
        self.prompts: list[str] = []
        self.respostas: list[str] = []
        self.chamadas = 0

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500,
                 system_prompt: str | None = None, json_mode: bool = False):
        self.chamadas += 1
        self.prompts.append((system_prompt or "") + "\n\n" + prompt)
        r = self.cliente.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens,
                                  system_prompt=system_prompt, json_mode=json_mode)
        self.respostas.append(r.text)
        if self.rastreador:
            self.rastreador.somar_tokens(r.prompt_tokens, r.completion_tokens, r.model, r.provider)
        return r

    def warmup(self) -> dict:
        fn = getattr(self.cliente, "warmup", None)
        return fn() if callable(fn) else {"warmed": False}


ENV_LIBERACAO_EXTERNA = "BANCADA_PERMITIR_EXTERNO"
VALOR_LIBERACAO_EXTERNA = "benchmark-publico"


def externo_liberado() -> bool:
    """True só quando a pessoa declarou que o material é público (questões do benchmark, sem dado de aluno)."""
    return os.environ.get(ENV_LIBERACAO_EXTERNA, "").strip() == VALOR_LIBERACAO_EXTERNA


class ProvedorExternoComEspera:
    """Groq do grupo (GroqLLMProvider) com espera longa no limite do plano gratuito.

    O provedor do grupo tenta de novo só 3 vezes, com 5 a 15 s de espera; no plano gratuito o limite por minuto
    precisa de até 1 minuto. Aqui a espera segue o cabeçalho retry-after (ou 20 s, 40 s, ...), até 8 tentativas.
    """

    provider_name = "groq"

    def __init__(self, modelo: str | None) -> None:
        from iris.core.llm_client import GroqLLMProvider

        self._prov = GroqLLMProvider(model=modelo)
        self.model = self._prov.model
        self.esperas_s = 0.0

    def is_available(self) -> bool:
        return self._prov.is_available()

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500,
                 system_prompt: str | None = None, json_mode: bool = False):
        import urllib.error

        for tentativa in range(8):
            try:
                return self._prov.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens,
                                           system_prompt=system_prompt, json_mode=json_mode)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and tentativa < 7:
                    corpo = ""
                    if e.code == 429:
                        try:
                            corpo = e.read().decode("utf-8", "replace")
                        except Exception:  # noqa: BLE001 - só para decidir se é cota do dia
                            corpo = ""
                        if "per day" in corpo or "TPD" in corpo or "RPD" in corpo:
                            # SystemExit não é pego pelo laço do benchmark: o processo para em vez de gravar 30 erros
                            raise SystemExit("cota diária do Groq esgotada; rodar de novo depois (continua de onde parou)") from e
                    espera = min(float(e.headers.get("retry-after") or 20 * (tentativa + 1)) + 2, 120)
                    print(f"   groq {e.code}, esperando {espera:.0f} s", flush=True)
                    self.esperas_s += espera
                    time.sleep(espera)
                    continue
                raise


def criar_cliente(provedor: str, modelo: str | None = None) -> ClienteRastreado:
    """Fábrica com trava: só extractive, eco ou ollama. API externa só com liberação explícita.

    A trava existe porque o pipeline pode receber material com dado de aluno. A única exceção é o Groq quando
    BANCADA_PERMITIR_EXTERNO=benchmark-publico (questões escolares públicas do Golden Benchmark, sem dado de
    aluno); quem usa a exceção deve registrar isso na saída (ver semana3/teste_d.py).
    """
    preparar_ambiente()
    provedor = provedor.lower()
    if provedor == "groq" and externo_liberado():
        if not os.environ.get("GROQ_API_KEY"):
            raise SystemExit("GROQ_API_KEY não está no ambiente.")
        return ClienteRastreado(ProvedorExternoComEspera(modelo), "groq")
    if provedor in {"groq", "openai", "anthropic"}:
        raise SystemExit("Provedor externo recusado pelo arnês: use extractive, eco ou ollama.")
    from iris.core.llm_client import HybridLLMClient

    if provedor == "extractive":
        base = HybridLLMClient(provider="extractive")
    elif provedor == "eco":
        base = ProvedorEco()
    elif provedor == "ollama":
        base = HybridLLMClient(provider="ollama", model=modelo or MODELO_PADRAO_OLLAMA)
        modelo_efetivo = base._primary.model  # type: ignore[attr-defined]
        instalados = base._primary.list_installed_models()  # type: ignore[attr-defined]
        if modelo_efetivo not in instalados:
            raise SystemExit(
                f"Modelo '{modelo_efetivo}' não está instalado no Ollama ({instalados or 'Ollama fora do ar'}). "
                f"No PC: ollama pull {modelo_efetivo}. Na VPS não use ollama para geração."
            )
    else:
        raise SystemExit(f"Provedor desconhecido: {provedor}")
    return ClienteRastreado(base, provedor)


def nome_modelo(cliente: ClienteRastreado) -> str:
    c = cliente.cliente
    prim = getattr(c, "_primary", c)
    return str(getattr(prim, "model", "desconhecido"))


def instalar_cliente_nos_agentes(cliente: ClienteRastreado) -> Callable[[], None]:
    """Faz as fábricas get_llm_client dos agentes do grupo devolverem o cliente do arnês."""
    preparar_ambiente()
    import iris.agents.adapter_agent as aa
    import iris.agents.curriculum_extractor as ce

    orig_a, orig_c = aa.get_llm_client, ce.get_llm_client
    aa.get_llm_client = lambda *a, **k: cliente  # type: ignore[assignment]
    ce.get_llm_client = lambda *a, **k: cliente  # type: ignore[assignment]

    def desfazer() -> None:
        aa.get_llm_client, ce.get_llm_client = orig_a, orig_c

    return desfazer


def escrever_json(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def escrever_jsonl(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        for l in linhas:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
