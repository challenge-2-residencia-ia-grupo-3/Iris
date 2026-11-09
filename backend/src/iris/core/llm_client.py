"""Camada de abstração híbrida de LLM (História 4.2.3 / Issue #43).

Permite alternar transparentemente entre:
1. `ollama`: Execução 100% local (Llama 3.1 8B, Qwen 3 8B, etc.) via Ollama HTTP API,
   garantindo privacidade estrita (LGPD / RNF-01) e custo zero de API para toda a equipe.
2. `groq`: Execução via API externa compatível com OpenAI (Groq Cloud) para testes rápidos em nuvem.
3. `extractive`: Modo determinístico offline para testes automatizados (CI/CD) sem GPU ou rede,
   sintetizando respostas diretamente das sentenças dos trechos `[T1]..[Tk]` entregues no prompt.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from iris.config import get_settings

FRASE_SEM_RESPOSTA = "Não encontrei nos documentos da base informação suficiente para responder."


@dataclass(frozen=True)
class LLMResponse:
    """Resposta padronizada de qualquer provedor de LLM da plataforma Íris."""

    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    raw_usage: dict[str, Any] = field(default_factory=dict)

    @property
    def llm_id(self) -> str:
        return f"{self.provider}:{self.model}"


def strip_thinking_tags(text: str) -> str:
    """Remove blocos `<think>...</think>` emitidos por modelos de raciocínio (ex.: Qwen3/DeepSeek)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class BaseLLMProvider(ABC):
    """Interface base para provedores de modelos de linguagem."""

    provider_name: str = "base"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        """Gera texto a partir de um prompt com temperatura controlada."""

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se o provedor está acessível e configurado no ambiente."""


class OllamaLLMProvider(BaseLLMProvider):
    """Provedor para execução de LLM local via Ollama (`http://127.0.0.1:11434`)."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or os.environ.get("OLLAMA_URL") or settings.ollama_url).rstrip("/")
        self.timeout_seconds = timeout_seconds

        explicit_model = model or os.environ.get("IRIS_LLM_MODEL") or os.environ.get("RAG_LLM_MODELO")
        if explicit_model:
            self.model = explicit_model
        else:
            # Detecta automaticamente modelos Llama 3 já instalados no Ollama local
            installed = self.list_installed_models()
            if settings.llm_model in installed:
                self.model = settings.llm_model
            elif "llama3:latest" in installed:
                self.model = "llama3:latest"
            elif any("llama3" in m for m in installed):
                self.model = next(m for m in installed if "llama3" in m)
            elif installed:
                self.model = installed[0]
            else:
                self.model = settings.llm_model

    def list_installed_models(self) -> list[str]:
        """Retorna a lista de modelos instalados no servidor Ollama local."""
        req = urllib.request.Request(
            f"{self.base_url}/api/tags",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    def is_available(self) -> bool:
        """Verifica se o daemon do Ollama responde na porta local."""
        req = urllib.request.Request(
            f"{self.base_url}/api/tags",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _resolve_model(self) -> str:
        """Seleciona o modelo configurado ou faz fallback para um modelo já instalado no Ollama."""
        installed = self.list_installed_models()
        if not installed:
            return self.model
        if self.model in installed:
            return self.model
        # Verifica correspondência por prefixo (ex.: 'llama3.1' -> 'llama3.1:latest')
        base_prefix = self.model.split(":")[0]
        for candidate in installed:
            if candidate.startswith(base_prefix):
                return candidate
        # Se houver outro modelo instalado (ex.: qwen3:8b), usa-o como fallback local
        return installed[0]

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        t0 = time.perf_counter()
        effective_model = self._resolve_model()
        payload = json.dumps(
            {
                "model": effective_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "seed": 42,
                },
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Não foi possível conectar ao Ollama em {self.base_url} (modelo '{effective_model}'). "
                f"Execute './scripts/setup_ollama.sh {self.model}' ou 'ollama serve'. Detalhe: {exc}"
            ) from exc

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        cleaned = strip_thinking_tags(data.get("response", ""))
        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        return LLMResponse(
            text=cleaned,
            provider=self.provider_name,
            model=effective_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            raw_usage=usage,
        )


class GroqLLMProvider(BaseLLMProvider):
    """Provedor para execução via API externa (Groq Cloud compatível com OpenAI)."""

    provider_name = "groq"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.groq.com/openai/v1/chat/completions",
        timeout_seconds: int = 120,
    ) -> None:
        settings = get_settings()
        default_groq_model = "llama-3.3-70b-versatile"
        env_model = os.environ.get("IRIS_LLM_MODEL") or os.environ.get("RAG_LLM_MODELO")
        self.model = model or env_model or default_groq_model
        self.api_key = api_key if api_key is not None else (os.environ.get("GROQ_API_KEY") or settings.groq_api_key)
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError(
                "GROQ_API_KEY não configurada no ambiente. Configure no .env ou use IRIS_LLM_PROVIDER=ollama."
            )

        t0 = time.perf_counter()
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "iris-rag/0.1",
            },
        )

        data: dict[str, Any] = {}
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        raw_content = data["choices"][0]["message"]["content"]
        cleaned = strip_thinking_tags(raw_content)
        usage = data.get("usage", {})
        return LLMResponse(
            text=cleaned,
            provider=self.provider_name,
            model=self.model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            raw_usage=usage,
        )


class ExtractiveFallbackLLMProvider(BaseLLMProvider):
    """Provedor extrativo determinístico para execução offline / CI sem GPU ou API externa.

    Analisa os blocos `[T1]..[Tk]` entregues no prompt do RAG, seleciona as sentenças com
    maior aderência lexical à pergunta (ignorando trechos com `AVISO DE USO`) e formata
    cada frase com sua respectiva citação `[Tn]`.
    """

    provider_name = "extractive"

    def __init__(self, model: str = "deterministic-bm25-extractive") -> None:
        self.model = model

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        t0 = time.perf_counter()
        q_match = re.search(r"PERGUNTA:\s*(.+?)\s*\n\nRESPOSTA:", prompt, flags=re.DOTALL)
        pergunta = q_match.group(1).strip() if q_match else ""

        # Extrai blocos [T1]..[Tk]
        partes = re.split(r"\n(?=\[T\d+\]\s)", prompt)
        blocos: list[tuple[int, str, bool]] = []
        for p in partes:
            m = re.match(r"\[T(\d+)\]\s*([^\n]+)\n(.*)", p.strip(), flags=re.DOTALL)
            if not m:
                continue
            idx = int(m.group(1))
            corpo = m.group(3)
            corpo_sem_pergunta = corpo.split("\n\nPERGUNTA:")[0].strip()
            tem_aviso = "AVISO DE USO:" in corpo_sem_pergunta
            if tem_aviso:
                linhas = [ln for ln in corpo_sem_pergunta.splitlines() if not ln.startswith("AVISO DE USO:")]
                corpo_sem_pergunta = "\n".join(linhas).strip()
            blocos.append((idx, corpo_sem_pergunta, tem_aviso))

        q_tokens = {
            w.lower()
            for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", pergunta)
            if w.lower() not in {"como", "para", "qual", "quais", "aluno", "professores", "sobre", "fazer", "pode"}
        }

        candidatas: list[tuple[float, int, str]] = []
        for idx, texto_bloco, tem_aviso in blocos:
            if tem_aviso:
                continue
            frases = [
                f.strip()
                for f in re.split(r"(?<=[.!?])\s+|\n+", texto_bloco)
                if 35 <= len(f.strip()) <= 320 and not f.strip().startswith("#")
            ]
            for pos, f in enumerate(frases):
                f_tokens = {w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", f)}
                inter = len(q_tokens & f_tokens)
                score = inter * 2.0 + (1.0 / (idx + pos * 0.2))
                if inter > 0 or (not q_tokens and idx <= 2):
                    frase_limpa = f.rstrip(".!?").strip()
                    candidatas.append((score, idx, f"{frase_limpa} [T{idx}]."))

        candidatas.sort(key=lambda x: x[0], reverse=True)
        selecionadas: list[str] = []
        usados: set[str] = set()
        for score, idx, frase_citada in candidatas:
            chave = frase_citada[:50].lower()
            if chave not in usados and score >= 1.5:
                usados.add(chave)
                selecionadas.append(frase_citada)
            if len(selecionadas) >= 3:
                break

        if not selecionadas:
            texto_final = FRASE_SEM_RESPOSTA
        else:
            texto_final = " ".join(selecionadas)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        p_toks = len(prompt.split())
        c_toks = len(texto_final.split())
        return LLMResponse(
            text=texto_final,
            provider=self.provider_name,
            model=self.model,
            prompt_tokens=p_toks,
            completion_tokens=c_toks,
            latency_ms=latency_ms,
            raw_usage={"prompt_tokens": p_toks, "completion_tokens": c_toks},
        )


class HybridLLMClient:
    """Cliente unificado de LLM com seleção de provedor e fallback resiliente."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        allow_fallback_to_extractive: bool = False,
    ) -> None:
        settings = get_settings()
        self.provider_name = (
            provider
            or os.environ.get("IRIS_LLM_PROVIDER")
            or os.environ.get("RAG_LLM")
            or settings.llm_provider
        ).lower()
        self.model = model
        self.allow_fallback_to_extractive = allow_fallback_to_extractive
        self._primary = self._build_provider(self.provider_name, self.model)

    @staticmethod
    def _build_provider(provider_name: str, model: str | None = None) -> BaseLLMProvider:
        if provider_name == "ollama":
            return OllamaLLMProvider(model=model)
        if provider_name == "groq":
            return GroqLLMProvider(model=model)
        if provider_name in {"extractive", "mock", "offline"}:
            return ExtractiveFallbackLLMProvider(model=model or "deterministic-bm25-extractive")
        raise ValueError(
            f"Provedor de LLM desconhecido: {provider_name!r}. Use 'ollama', 'groq' ou 'extractive'."
        )

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        try:
            return self._primary.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            if self.allow_fallback_to_extractive and not isinstance(
                self._primary, ExtractiveFallbackLLMProvider
            ):
                fallback = ExtractiveFallbackLLMProvider()
                return fallback.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
            raise

    def status(self) -> dict[str, Any]:
        """Retorna diagnóstico de conectividade dos provedores de LLM."""
        ollama_prov = OllamaLLMProvider(model=self.model)
        groq_prov = GroqLLMProvider(model=self.model)
        return {
            "configured_provider": self.provider_name,
            "primary_available": self._primary.is_available(),
            "ollama_online": ollama_prov.is_available(),
            "ollama_url": ollama_prov.base_url,
            "ollama_installed_models": ollama_prov.list_installed_models(),
            "groq_configured": groq_prov.is_available(),
        }


def get_llm_client(
    provider: str | None = None,
    model: str | None = None,
    allow_fallback_to_extractive: bool = False,
) -> HybridLLMClient:
    """Factory padrão para obter o cliente híbrido de LLM."""
    return HybridLLMClient(
        provider=provider,
        model=model,
        allow_fallback_to_extractive=allow_fallback_to_extractive,
    )
