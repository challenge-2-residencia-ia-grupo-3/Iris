"""rastro_producao.py: protótipo de registrador de METADADOS por requisição para o Íris em produção.

Analogia: é o diário de bordo de um avião. Ele anota a hora, quanto combustível gastou, quanto tempo
cada trecho levou e se houve pouso de emergência. Ele NUNCA anota o que os passageiros conversaram.
Aqui, "o que os passageiros conversaram" é o enunciado, o texto adaptado, o perfil e qualquer nome.

Regras de privacidade do grupo que este arquivo segue (ver PROPOSTA.md):
  * RNF-01 / issue #35 (Zero-Database): nada do material nem do perfil fica gravado; sem banco.
  * RNF-02 / issue #37 (não-retenção de payloads em log): só métricas operacionais.
  * RNF-03 / issue #28: nada clínico (CID, laudo, medicação).

Como o registrador garante isso (camadas, da mais forte para a mais fraca):
  1. LISTA FECHADA DE CAMPOS: só entram chaves declaradas no ESQUEMA; qualquer outra é recusada.
  2. TIPOS E FAIXAS: número tem faixa (ex.: nivel 1 a 3); texto só é aceito se for de uma lista fechada
     (ex.: id de característica do catálogo) ou de um padrão curto sem espaço (ex.: nome do modelo).
     Não existe campo de texto livre: "motivo da recusa" é escolhido numa lista, não digitado.
  3. DETECTOR DE DADO PESSOAL: CPF, telefone, e-mail, matrícula, CID e "Nome Sobrenome" são recusados
     mesmo que caibam no padrão.
  4. SENTINELA DO MATERIAL: durante a requisição o registrador guarda EM MEMÓRIA as palavras do material
     (nunca em disco) e recusa qualquer valor de texto semiaberto que contenha uma delas. Ao fim da
     requisição a sentinela é apagada.
  5. A mensagem de recusa nunca repete o valor recusado (senão o próprio aviso vazaria o dado).

Modos (variável de ambiente IRIS_RASTRO_PRODUCAO):
  desligado  (padrão) nada é gravado; o registrador vira um "faz nada".
  agregado   só contadores por dia (sem id de requisição); é o modo recomendado.
  eventos    uma linha JSON por evento, em arquivo diário local, apagado após N dias.

Só usa a biblioteca padrão do Python, para o grupo poder copiar sem dependência nova.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

VERSAO_ESQUEMA = 1

# ---------------------------------------------------------------- listas fechadas
# Ids do catálogo do grupo (rag/catalogs/tdah_caracteristicas_funcionais.json, commit 65e1f09).
# Em produção o grupo deve passar a lista lida do próprio catálogo (fonte única, DEP-OC-04).
CARACTERISTICAS_PADRAO = (
    "sobrecarga_memoria_trabalho_comandos_multiplos",
    "retencao_dados_intermediarios_problemas_multietapas",
    "atencao_sustentada_textos_longos",
    "distratibilidade_poluicao_visual_layout",
    "impulsividade_leitura_superficial_negacoes",
    "organizacao_sequencial_expressao_escrita",
    "fadiga_executiva_autorregulacao_provas_extensas",
    "flexibilidade_cognitiva_alternancia_topicos",
    "bloqueio_iniciacao_tarefas_abertas",
    "ritmo_processamento_pressao_temporal",
)

ETAPAS = (
    "upload_tamanho", "extracao_documento", "filtro_pii", "validacao_conteudo", "decomposicao_estrutural",
    "selecao_caracteristicas", "perfil_pedagogico", "extrator_curricular", "busca_rag", "contexto_rag",
    "agente_estrategista", "agente_adaptador", "laudo_isolamento_escopo", "saida_de_reserva",
    "agente_auditor", "exportacao",
)
STATUS_ETAPA = ("ok", "erro", "pulada")
FORMATOS = ("texto", "txt", "pdf", "docx")
FAIXAS_TAMANHO = ("ate_500", "500_2000", "2000_10000", "acima_10000")
PROVEDORES = ("ollama", "groq", "extractive", "eco", "outro")
MOTIVOS_RESERVA = ("nenhum", "provedor_sem_modelo", "escopo_reprovado", "falha_llm")
# categorias das violações do laudo de escopo (iris/eval/escopo.py), sem o conteúdo da violação
VIOLACOES = ("conceito_ausente", "palavra_ausente", "palavra_fora_vocabulario", "ordem_alterada",
             "texto_alterado_alem_destaque", "outra")
DECISOES = ("aceitou", "editou", "recusou", "sem_retorno")
# Motivo de recusa: lista fechada, escolhida num menu da tela de revisão (#22). Sem caixa de texto.
MOTIVOS_RECUSA = (
    "mudou_o_que_a_questao_avalia",      # quebrou a trava curricular
    "andaime_nao_ajuda_esta_caracteristica",
    "linguagem_infantilizada",
    "formatacao_quebrada",
    "erro_de_conteudo",
    "demorou_demais",
    "outro",
)
TIPOS = ("requisicao", "adaptacao", "retorno")

PADRAO_MODELO = re.compile(r"^[a-z0-9][a-z0-9._:/\-]{0,63}$")
# Códigos de erro: lista fechada. Os códigos MaterialValidationError/ProfileError do grupo (grep code="..."
# no commit 65e1f09) + nomes de exceção comuns. Qualquer outra coisa vira "outro" via codigo_erro().
CODIGOS_ERRO = (
    "CATALOG_NOT_FOUND", "CLINICAL_OR_EXTRA_FIELD_FORBIDDEN", "CONTEXT_WINDOW_EXCEEDED", "CORRUPTED_DOCX",
    "CORRUPTED_PDF", "DECODE_ERROR", "EMPTY_CHARACTERISTIC_SELECTION", "EMPTY_FILE", "EMPTY_TEXT",
    "FILE_TOO_LARGE", "INVALID_CATALOG_ID_TYPE", "INVALID_CHARACTERISTIC_ID", "INVALID_PAYLOAD",
    "INVALID_SELECTION_TYPE", "INVALID_TEXT_TYPE", "LIBRARY_NOT_AVAILABLE", "MISSING_FILENAME",
    "NO_READABLE_TEXT", "TEXT_TOO_SHORT", "UNKNOWN_CHARACTERISTIC_ID", "UNSUPPORTED_FORMAT",
    "ValidationError", "ValueError", "KeyError", "TypeError", "JSONDecodeError", "TimeoutError",
    "ReadTimeout", "ConnectError", "ConnectionError", "HTTPStatusError", "RuntimeError", "outro",
)


def codigo_erro(exc_ou_codigo: Any) -> str:
    """Converte exceção ou código em um item da lista fechada (nunca a mensagem da exceção)."""
    c = exc_ou_codigo if isinstance(exc_ou_codigo, str) else (getattr(exc_ou_codigo, "code", None)
                                                              or type(exc_ou_codigo).__name__)
    return c if c in CODIGOS_ERRO else "outro"
PADRAO_HEX16 = re.compile(r"^[0-9a-f]{16}$")
PADRAO_HEX32 = re.compile(r"^[0-9a-f]{32}$")
PADRAO_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------- detector de dado pessoal
_PII = (
    ("cpf", re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")),
    ("telefone", re.compile(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("matricula", re.compile(r"(?i)matr[ií]cula|\b\d{4}-[A-Z]+-\d+\b")),
    ("cid", re.compile(r"(?i)\bCID[-\s]?1?[01]?\b|\bF9\d(\.\d)?\b")),
    ("nome_proprio", re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+)+")),
)


def parece_dado_pessoal(valor: str) -> str | None:
    """Devolve o tipo de dado pessoal detectado (ou None). Nunca devolve o trecho."""
    for nome, rx in _PII:
        if rx.search(valor):
            return nome
    return None


class CampoRecusado(ValueError):
    """Campo recusado pelo esquema. A mensagem NUNCA contém o valor recusado."""

    def __init__(self, campo: str, motivo: str) -> None:
        self.campo, self.motivo = campo, motivo
        super().__init__(f"campo '{campo}' recusado: {motivo}")


# ---------------------------------------------------------------- esquema
def _inteiro(minimo: int, maximo: int, passo: int = 1):
    def v(campo: str, x: Any, ctx: dict) -> int:
        if isinstance(x, bool) or not isinstance(x, int):
            raise CampoRecusado(campo, "esperado número inteiro")
        if not minimo <= x <= maximo:
            raise CampoRecusado(campo, f"fora da faixa {minimo}..{maximo}")
        if x % passo:
            raise CampoRecusado(campo, f"precisa ser múltiplo de {passo} (arredonde antes)")
        return x
    return v


def _real(minimo: float, maximo: float, casas: int = 1):
    def v(campo: str, x: Any, ctx: dict) -> float:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise CampoRecusado(campo, "esperado número")
        if not minimo <= float(x) <= maximo:
            raise CampoRecusado(campo, f"fora da faixa {minimo}..{maximo}")
        return round(float(x), casas)
    return v


def _booleano(campo: str, x: Any, ctx: dict) -> bool:
    if not isinstance(x, bool):
        raise CampoRecusado(campo, "esperado verdadeiro/falso")
    return x


def _texto_basico(campo: str, x: Any, checar_pii: bool = True) -> str:
    if not isinstance(x, str):
        raise CampoRecusado(campo, "esperado texto curto")
    if any(c.isspace() for c in x) or len(x) > 64:
        raise CampoRecusado(campo, "texto livre não é aceito (espaço ou mais de 64 caracteres)")
    tipo = parece_dado_pessoal(x) if checar_pii else None
    if tipo:
        raise CampoRecusado(campo, f"parece dado pessoal ({tipo})")
    return x


def _lista_fechada(opcoes_ou_chave: Iterable[str] | str):
    def v(campo: str, x: Any, ctx: dict) -> str:
        opcoes = ctx[opcoes_ou_chave] if isinstance(opcoes_ou_chave, str) else tuple(opcoes_ou_chave)
        if not isinstance(x, str):
            raise CampoRecusado(campo, "esperado um valor da lista fechada")
        _texto_basico(campo, x)
        if x not in opcoes:
            raise CampoRecusado(campo, "valor fora da lista fechada")
        return x
    return v


def _padrao(rx: re.Pattern, semiaberto: bool = False, checar_pii: bool = True):
    """semiaberto=True: o valor é escolhido pelo sistema, mas não de uma lista; passa pela sentinela.

    checar_pii=False só para formatos que não conseguem carregar texto (hexadecimal de tamanho fixo,
    data): um hash pode ter 11 dígitos seguidos e seria confundido com CPF.
    """
    def v(campo: str, x: Any, ctx: dict) -> str:
        _texto_basico(campo, x, checar_pii)
        if not rx.match(x):
            raise CampoRecusado(campo, "formato não permitido")
        if semiaberto and _bate_sentinela(x, ctx.get("sentinela") or frozenset()):
            raise CampoRecusado(campo, "contém palavra do material desta requisição")
        return x
    return v


def _lista_de(validador, maximo: int):
    def v(campo: str, x: Any, ctx: dict) -> list:
        if not isinstance(x, (list, tuple)) or len(x) > maximo:
            raise CampoRecusado(campo, f"esperada lista com até {maximo} itens")
        return [validador(campo, i, ctx) for i in x]
    return v


def _etapa_item(campo: str, x: Any, ctx: dict) -> dict:
    if not isinstance(x, dict) or set(x) - {"etapa", "ms", "status"} or "etapa" not in x:
        raise CampoRecusado(campo, "item de etapa só aceita as chaves etapa, ms e status")
    return {"etapa": _lista_fechada(ETAPAS)(campo, x["etapa"], ctx),
            "ms": _real(0, 600_000, 1)(campo, x.get("ms", 0.0), ctx),
            "status": _lista_fechada(STATUS_ETAPA)(campo, x.get("status", "ok"), ctx)}


COMUNS = {
    "tipo": _lista_fechada(TIPOS),
    "versao_esquema": _inteiro(1, 1),
    "sintetico": _booleano,
    "dia": _padrao(PADRAO_DIA, checar_pii=False),
    "hora": _inteiro(0, 23),
    "id_requisicao": _padrao(PADRAO_HEX32, checar_pii=False),
}
ESQUEMA: dict[str, dict[str, Callable]] = {
    "requisicao": COMUNS | {
        "material_hmac": _padrao(PADRAO_HEX16, checar_pii=False),
        "formato": _lista_fechada(FORMATOS),
        "faixa_tamanho": _lista_fechada(FAIXAS_TAMANHO),
        "n_questoes": _inteiro(0, 500),
        "n_pii_substituidos": _inteiro(0, 10_000),
        "etapas": _lista_de(_etapa_item, 40),
        "erro_codigo": _lista_fechada(CODIGOS_ERRO),
        "n_campos_recusados": _inteiro(0, 10_000),
    },
    "adaptacao": COMUNS | {
        "questao_ordem": _inteiro(1, 500),
        "caracteristica": _lista_fechada("caracteristicas"),
        "nivel": _inteiro(1, 3),
        "provedor": _lista_fechada(PROVEDORES),
        "modelo": _padrao(PADRAO_MODELO, semiaberto=True),  # vem da configuração; a sentinela é só cinto extra
        "etapas": _lista_de(_etapa_item, 40),
        "tokens_entrada": _inteiro(0, 500_000),
        "tokens_saida": _inteiro(0, 500_000),
        "usou_reserva": _booleano,
        "motivo_reserva": _lista_fechada(MOTIVOS_RESERVA),
        "escopo_aprovado": _booleano,
        "violacoes": _lista_de(_lista_fechada(VIOLACOES), 10),
        "trava_recall": _real(0.0, 1.0, 3),
        "dentro_limite_rnf07": _booleano,
        "erro_codigo": _lista_fechada(CODIGOS_ERRO),
        "n_campos_recusados": _inteiro(0, 10_000),
    },
    # O retorno chega do navegador. Leva característica, nível e reserva junto para o modo 'agregado'
    # não precisar cruzar nada com a adaptação (o navegador já tem esses dados na sessão).
    "retorno": COMUNS | {
        "caracteristica": _lista_fechada("caracteristicas"),
        "nivel": _inteiro(1, 3),
        "usou_reserva": _booleano,
        "decisao": _lista_fechada(DECISOES),
        "pct_alterado": _inteiro(0, 100, passo=5),
        "motivo_recusa": _lista_fechada(MOTIVOS_RECUSA),
        "segundos_ate_decisao": _inteiro(0, 3600, passo=10),
    },
}
OBRIGATORIOS = {
    "requisicao": {"tipo", "versao_esquema", "dia"},
    "adaptacao": {"tipo", "versao_esquema", "dia", "caracteristica", "nivel"},
    "retorno": {"tipo", "versao_esquema", "dia", "caracteristica", "nivel", "decisao"},
}


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def palavras_sentinela(texto: str, minimo: int = 4) -> frozenset[str]:
    """Palavras do material (normalizadas) que nenhum campo semiaberto pode conter. Só em memória."""
    return frozenset(p for p in re.findall(r"[a-z0-9]+", _normalizar(texto or "")) if len(p) >= minimo)


def _bate_sentinela(valor: str, sentinela: frozenset[str]) -> bool:
    if not sentinela:
        return False
    partes = [p for p in re.findall(r"[a-z0-9]+", _normalizar(valor)) if len(p) >= 4]
    alvo = _normalizar(valor)
    return any(p in sentinela for p in partes) or any(w in alvo for w in sentinela if len(w) >= 6)


def validar_registro(registro: dict, caracteristicas: Iterable[str] = CARACTERISTICAS_PADRAO,
                     sentinela: frozenset[str] = frozenset(), estrito: bool = True) -> tuple[dict, int]:
    """Valida um registro contra o ESQUEMA. Devolve (registro_limpo, n_campos_recusados).

    estrito=True: o primeiro campo recusado levanta CampoRecusado (para testes e desenvolvimento).
    estrito=False: o campo recusado é descartado e contado (produção: nunca derrubar a requisição).
    Campos obrigatórios ausentes ou inválidos sempre levantam erro.
    """
    if not isinstance(registro, dict):
        raise CampoRecusado("registro", "esperado dicionário")
    tipo = registro.get("tipo")
    if tipo not in ESQUEMA:
        raise CampoRecusado("tipo", "tipo de registro desconhecido")
    ctx = {"caracteristicas": tuple(caracteristicas), "sentinela": sentinela}
    esquema, limpo, recusados = ESQUEMA[tipo], {}, 0
    for chave, valor in registro.items():
        if valor is None:
            continue
        try:
            if not isinstance(chave, str) or chave not in esquema:
                # o nome da chave pode ser o próprio dado ("Fulana": 1): não repetimos a chave na mensagem
                raise CampoRecusado("(chave fora do esquema)", "chave não declarada no esquema")
            limpo[chave] = esquema[chave](chave, valor, ctx)
        except CampoRecusado:
            if estrito or chave in OBRIGATORIOS[tipo]:
                raise
            recusados += 1
    faltando = OBRIGATORIOS[tipo] - set(limpo)
    if faltando:
        raise CampoRecusado(",".join(sorted(faltando)), "campo obrigatório ausente")
    return limpo, recusados


# ---------------------------------------------------------------- utilidades de metadado
def faixa_tamanho(n_caracteres: int) -> str:
    if n_caracteres <= 500:
        return "ate_500"
    if n_caracteres <= 2000:
        return "500_2000"
    if n_caracteres <= 10_000:
        return "2000_10000"
    return "acima_10000"


def pct_alterado(sugerido: str, final: str) -> int:
    """% de caracteres alterados pela professora, arredondado de 5 em 5.

    Feito para rodar NO NAVEGADOR (ou aqui, só em memória): o servidor recebe só o número.
    Usa distância de edição aproximada pelo difflib (stdlib).
    """
    import difflib

    if not sugerido and not final:
        return 0
    sm = difflib.SequenceMatcher(None, sugerido, final, autojunk=False)
    iguais = sum(b.size for b in sm.get_matching_blocks())
    base = max(len(sugerido), len(final), 1)
    pct = 100.0 * (1 - iguais / base)
    return int(min(100, max(0, 5 * round(pct / 5))))


def categoria_violacao(texto_violacao: str) -> str:
    """Converte a frase de violação do laudo do grupo (que pode citar palavras do texto) em categoria."""
    t = texto_violacao.casefold()
    if t.startswith("conceito da trava"):
        return "conceito_ausente"
    if t.startswith("palavra do original ausente"):
        return "palavra_ausente"
    if t.startswith("palavra fora do vocabul"):
        return "palavra_fora_vocabulario"
    if t.startswith("ordem das palavras"):
        return "ordem_alterada"
    if t.startswith("texto alterado al"):
        return "texto_alterado_alem_destaque"
    return "outra"


def motivo_reserva(motivo_do_grupo: str | None) -> str:
    if not motivo_do_grupo:
        return "nenhum"
    if motivo_do_grupo.startswith("falha_llm"):
        return "falha_llm"  # o nome da exceção vai para erro_codigo, não aqui
    return motivo_do_grupo if motivo_do_grupo in MOTIVOS_RESERVA else "falha_llm"


# ---------------------------------------------------------------- destino (onde grava)
class _Destino:
    """Arquivo local diário, permissão 600, com apagamento automático após `retencao_dias`."""

    def __init__(self, pasta: Path, modo: str, retencao_dias: int) -> None:
        self.pasta, self.modo, self.retencao_dias = Path(pasta), modo, retencao_dias
        self.contadores: dict[str, dict[str, int]] = {}

    def _arquivo(self, dia: str, prefixo: str) -> Path:
        return self.pasta / f"{prefixo}-{dia}.jsonl"

    def purgar(self, hoje: date | None = None) -> list[str]:
        """Apaga arquivos mais velhos que a retenção. Devolve os nomes apagados."""
        hoje = hoje or date.today()
        apagados = []
        if not self.pasta.is_dir():
            return apagados
        limite = hoje - timedelta(days=self.retencao_dias)
        for f in self.pasta.glob("*-????-??-??.jsonl"):
            try:
                d = date.fromisoformat(f.stem[-10:])
            except ValueError:
                continue
            if d < limite:
                f.unlink()
                apagados.append(f.name)
        return apagados

    def escrever(self, registro: dict) -> None:
        if self.modo == "eventos":
            self.pasta.mkdir(parents=True, exist_ok=True)
            arq = self._arquivo(registro["dia"], "eventos")
            novo = not arq.exists()
            with arq.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")
            if novo:
                os.chmod(arq, 0o600)
        elif self.modo == "agregado":
            # só contadores; nada de id de requisição nem de hash de material
            chave = self._chave_agregada(registro)
            if chave:
                dia = self.contadores.setdefault(registro["dia"], {})
                dia[chave] = dia.get(chave, 0) + 1

    @staticmethod
    def _chave_agregada(r: dict) -> str | None:
        if r["tipo"] == "retorno":
            extra = r.get("motivo_recusa") or (f"pct{r['pct_alterado']}" if "pct_alterado" in r else "")
            return f"retorno|{r['caracteristica']}|n{r['nivel']}|{r['decisao']}|{extra}"
        if r["tipo"] == "adaptacao":
            return (f"adaptacao|{r['caracteristica']}|n{r['nivel']}|reserva={r.get('usou_reserva')}|"
                    f"escopo={r.get('escopo_aprovado')}")
        return None

    def descarregar(self) -> None:
        """Modo agregado: grava os contadores do dia (chamar 1x por hora ou ao desligar o servidor)."""
        if self.modo != "agregado" or not self.contadores:
            return
        self.pasta.mkdir(parents=True, exist_ok=True)
        for dia, cont in self.contadores.items():
            arq = self._arquivo(dia, "agregado")
            antigo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
            for k, v in cont.items():
                antigo[k] = antigo.get(k, 0) + v
            arq.write_text(json.dumps(antigo, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            os.chmod(arq, 0o600)
        self.contadores.clear()


# ---------------------------------------------------------------- registrador
class RegistradorProducao:
    """Registrador de metadados por requisição.

    Uso pensado para as rotas da API (o grupo pluga depois; aqui a bancada exercita):

        reg = RegistradorProducao.do_ambiente()
        with reg.requisicao(texto_material, formato="pdf") as req:
            with req.etapa("filtro_pii"):
                texto, n = sanitize_pii(texto)
            req.definir(n_pii_substituidos=n)
            with req.questao(1, caracteristica, nivel) as q:
                with q.etapa("agente_adaptador"):
                    res = agente.adapt(pedido)
                q.definir(usou_reserva=res.telemetry.used_fallback, ...)
        # o navegador devolve depois:
        reg.retorno(caracteristica=..., nivel=2, decisao="editou", pct_alterado=35)
    """

    def __init__(self, modo: str = "desligado", pasta: Path | str | None = None, retencao_dias: int = 30,
                 caracteristicas: Iterable[str] = CARACTERISTICAS_PADRAO, estrito: bool = False,
                 sintetico: bool = False, relogio: Callable[[], datetime] | None = None) -> None:
        if modo not in ("desligado", "agregado", "eventos"):
            raise ValueError("modo deve ser desligado, agregado ou eventos")
        if modo != "desligado" and pasta is None:
            raise ValueError("modo ligado exige uma pasta local")
        if not 1 <= int(retencao_dias) <= 90:
            raise ValueError("retenção entre 1 e 90 dias")
        self.modo = modo
        self.caracteristicas = tuple(caracteristicas)
        self.estrito = estrito
        self.sintetico = sintetico
        self.relogio = relogio or (lambda: datetime.now(timezone.utc))
        self.destino = _Destino(Path(pasta), modo, int(retencao_dias)) if pasta is not None else None
        self.memoria: list[dict] = []  # cópia em memória do que foi aceito (para a bancada auditar)
        self.recusas = 0
        # chave do HMAC do material: aleatória, só em memória, troca por dia -> o hash não pode ser
        # recalculado depois por ninguém (nem por quem tiver a prova original e o arquivo de log)
        self._chave: tuple[str, bytes] | None = None
        if self.destino:
            self.destino.purgar(self.relogio().date())

    @classmethod
    def do_ambiente(cls, **kw) -> "RegistradorProducao":
        """Lê IRIS_RASTRO_PRODUCAO (desligado|agregado|eventos), IRIS_RASTRO_DIR e IRIS_RASTRO_RETENCAO_DIAS."""
        modo = os.environ.get("IRIS_RASTRO_PRODUCAO", "desligado").strip().lower() or "desligado"
        pasta = os.environ.get("IRIS_RASTRO_DIR")
        dias = int(os.environ.get("IRIS_RASTRO_RETENCAO_DIAS", "30"))
        if modo != "desligado" and not pasta:
            modo = "desligado"  # sem pasta explícita, não grava (opt-in de verdade)
        return cls(modo=modo, pasta=pasta, retencao_dias=dias, **kw)

    @property
    def ligado(self) -> bool:
        return self.modo != "desligado"

    def _hmac_material(self, texto: str) -> str:
        hoje = self.relogio().date().isoformat()
        if not self._chave or self._chave[0] != hoje:
            self._chave = (hoje, secrets.token_bytes(32))
        return hmac.new(self._chave[1], (texto or "").encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    def _base(self, tipo: str) -> dict:
        agora = self.relogio()
        b = {"tipo": tipo, "versao_esquema": VERSAO_ESQUEMA, "dia": agora.date().isoformat(), "hora": agora.hour}
        if self.sintetico:
            b["sintetico"] = True
        return b

    def gravar(self, registro: dict, sentinela: frozenset[str] = frozenset()) -> dict | None:
        """Valida e grava. Em modo não estrito, campos ruins são descartados e contados."""
        try:
            limpo, n_rec = validar_registro(registro, self.caracteristicas, sentinela, self.estrito)
        except CampoRecusado:
            self.recusas += 1
            if self.estrito:
                raise
            return None  # registro inteiro descartado (faltou campo obrigatório)
        self.recusas += n_rec
        if n_rec and "n_campos_recusados" in ESQUEMA[limpo["tipo"]]:
            limpo["n_campos_recusados"] = limpo.get("n_campos_recusados", 0) + n_rec
        self.memoria.append(limpo)
        if self.ligado and self.destino:
            self.destino.escrever(limpo)
        return limpo

    @contextmanager
    def requisicao(self, texto_material: str, formato: str = "texto"):
        req = _Requisicao(self, texto_material, formato)
        try:
            yield req
        except Exception as exc:
            req.campos["erro_codigo"] = codigo_erro(exc)
            raise
        finally:
            req.fechar()

    def retorno(self, caracteristica: str, nivel: int, decisao: str, pct_alterado: int | None = None,
                motivo_recusa: str | None = None, usou_reserva: bool | None = None,
                segundos_ate_decisao: int | None = None, id_requisicao: str | None = None) -> dict | None:
        """Retorno da professora. Coerência: pct só em 'editou', motivo só em 'recusou'."""
        if decisao != "editou":
            pct_alterado = None
        if decisao != "recusou":
            motivo_recusa = None
        r = self._base("retorno") | {"caracteristica": caracteristica, "nivel": nivel, "decisao": decisao,
                                     "pct_alterado": pct_alterado, "motivo_recusa": motivo_recusa,
                                     "usou_reserva": usou_reserva, "segundos_ate_decisao": segundos_ate_decisao}
        if self.modo == "eventos" and id_requisicao:
            r["id_requisicao"] = id_requisicao
        return self.gravar(r)

    def descarregar(self) -> None:
        if self.destino:
            self.destino.descarregar()


class _Cronometro:
    def __init__(self, lista: list, etapa: str) -> None:
        self.lista, self.etapa = lista, etapa

    @contextmanager
    def medir(self):
        t0 = time.perf_counter()
        status = "ok"
        try:
            yield
        except Exception:
            status = "erro"
            raise
        finally:
            self.lista.append({"etapa": self.etapa, "ms": round((time.perf_counter() - t0) * 1000, 1),
                               "status": status})


class _Questao:
    def __init__(self, req: "_Requisicao", ordem: int, caracteristica: str, nivel: int) -> None:
        self.req = req
        self.campos: dict[str, Any] = {"questao_ordem": ordem, "caracteristica": caracteristica, "nivel": nivel}
        self.etapas: list[dict] = []

    @contextmanager
    def etapa(self, nome: str):
        with _Cronometro(self.etapas, nome).medir():
            yield

    def definir(self, **campos: Any) -> None:
        self.campos.update(campos)


class _Requisicao:
    def __init__(self, reg: RegistradorProducao, texto: str, formato: str) -> None:
        self.reg = reg
        self.id = uuid.uuid4().hex  # aleatório: não deriva de nada da professora nem do material
        # a sentinela vive só enquanto a requisição estiver aberta
        self.sentinela: frozenset[str] = palavras_sentinela(texto)
        self.campos: dict[str, Any] = {"formato": formato, "faixa_tamanho": faixa_tamanho(len(texto or "")),
                                       "material_hmac": reg._hmac_material(texto) if reg.ligado or reg.estrito
                                       or reg.sintetico else None}
        self.etapas: list[dict] = []
        self.questoes: list[_Questao] = []

    @contextmanager
    def etapa(self, nome: str):
        with _Cronometro(self.etapas, nome).medir():
            yield

    def definir(self, **campos: Any) -> None:
        self.campos.update(campos)

    @contextmanager
    def questao(self, ordem: int, caracteristica: str, nivel: int):
        q = _Questao(self, ordem, caracteristica, nivel)
        self.questoes.append(q)
        try:
            yield q
        except Exception as exc:
            q.campos["erro_codigo"] = codigo_erro(exc)
            raise

    def fechar(self) -> None:
        base = self.reg._base("requisicao")
        id_ok = self.reg.modo == "eventos" or self.reg.sintetico
        r = base | self.campos | {"etapas": self.etapas}
        if id_ok:
            r["id_requisicao"] = self.id
        self.reg.gravar(r, self.sentinela)
        for q in self.questoes:
            a = self.reg._base("adaptacao") | q.campos | {"etapas": q.etapas}
            if id_ok:
                a["id_requisicao"] = self.id
            self.reg.gravar(a, self.sentinela)
        self.sentinela = frozenset()  # descarte: nada do material sobrevive à requisição


# ---------------------------------------------------------------- agregação para o painel
def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return [round(max(0.0, centro - meia), 4), round(min(1.0, centro + meia), 4)]


def bootstrap_media(valores: list[float], reps: int = 2000, semente: int = 7) -> list[float] | None:
    import random

    if len(valores) < 2:
        return None
    rnd = random.Random(semente)
    n = len(valores)
    medias = sorted(sum(rnd.choice(valores) for _ in range(n)) / n for _ in range(reps))
    return [round(medias[int(0.025 * reps)], 2), round(medias[int(0.975 * reps) - 1], 2)]


def _prop(k: int, n: int, k_min: int) -> dict:
    if n < k_min:
        return {"n": n, "suprimido": True, "motivo": f"menos de {k_min} casos: não exibir (evita identificar alguém)"}
    return {"n": n, "k": k, "p": round(k / n, 4), "ic95": wilson(k, n), "metodo_ic": "wilson"}


def _media(vals: list[float], n_total: int, k_min: int) -> dict:
    if len(vals) < k_min:
        return {"n": len(vals), "suprimido": True}
    return {"n": len(vals), "media": round(sum(vals) / len(vals), 2), "ic95": bootstrap_media(vals),
            "metodo_ic": "bootstrap 2000 reamostragens, semente 7"}


def _quantil(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(q * len(s)))], 1)


def agregar(registros: list[dict], k_min: int = 5) -> dict:
    """Transforma os eventos em métricas de produto. Células com menos de k_min casos são suprimidas."""
    adapt = [r for r in registros if r["tipo"] == "adaptacao"]
    reqs = [r for r in registros if r["tipo"] == "requisicao"]
    rets = [r for r in registros if r["tipo"] == "retorno"]
    com_retorno = [r for r in rets if r["decisao"] != "sem_retorno"]

    def bloco(rs: list[dict]) -> dict:
        cr = [r for r in rs if r["decisao"] != "sem_retorno"]
        n = len(cr)
        return {
            "n_retornos": len(rs),
            "n_com_decisao": n,
            "aceite_sem_edicao": _prop(sum(r["decisao"] == "aceitou" for r in cr), n, k_min),
            "aceite_com_ou_sem_edicao": _prop(sum(r["decisao"] in ("aceitou", "editou") for r in cr), n, k_min),
            "recusa": _prop(sum(r["decisao"] == "recusou" for r in cr), n, k_min),
            "edicao_media_pct_quando_editou": _media([r["pct_alterado"] for r in cr if r["decisao"] == "editou"
                                                      and "pct_alterado" in r], n, k_min),
            "sem_retorno": _prop(sum(r["decisao"] == "sem_retorno" for r in rs), len(rs), k_min),
        }

    por_carac = []
    for c in sorted({r["caracteristica"] for r in rets}):
        b = bloco([r for r in rets if r["caracteristica"] == c])
        por_carac.append({"caracteristica": c} | b)
    por_nivel = [{"nivel": nv} | bloco([r for r in rets if r["nivel"] == nv]) for nv in (1, 2, 3)]
    por_reserva = [{"usou_reserva": v} | bloco([r for r in rets if r.get("usou_reserva") is v]) for v in (False, True)]
    recusas = [r for r in com_retorno if r["decisao"] == "recusou"]
    motivos = [{"motivo": m} | _prop(sum(r.get("motivo_recusa") == m for r in recusas), len(recusas), k_min)
               for m in MOTIVOS_RECUSA]
    for m in motivos:
        m["contagem"] = sum(r.get("motivo_recusa") == m["motivo"] for r in recusas)

    etapas: dict[str, list[float]] = {}
    for r in adapt + reqs:
        for e in r.get("etapas", []):
            etapas.setdefault(e["etapa"], []).append(e["ms"])
    lat = [{"etapa": e, "n": len(v), "mediana_ms": _quantil(v, 0.5), "p90_ms": _quantil(v, 0.9)}
           for e, v in sorted(etapas.items(), key=lambda kv: ETAPAS.index(kv[0]))]
    tokens = [r.get("tokens_entrada", 0) + r.get("tokens_saida", 0) for r in adapt]
    return {
        "n_requisicoes": len(reqs),
        "n_adaptacoes": len(adapt),
        "n_retornos": len(rets),
        "n_materiais_distintos_no_dia_max": max((len({r["material_hmac"] for r in reqs if r["dia"] == d
                                                       and "material_hmac" in r}) for d in {r["dia"] for r in reqs}),
                                                default=0),
        "geral": bloco(rets),
        "por_caracteristica": por_carac,
        "por_nivel": por_nivel,
        "por_uso_de_reserva": por_reserva,
        "recusas_por_motivo": motivos,
        "reserva": _prop(sum(bool(r.get("usou_reserva")) for r in adapt), len(adapt), k_min),
        "motivos_reserva": {m: sum(r.get("motivo_reserva") == m for r in adapt) for m in MOTIVOS_RESERVA},
        "escopo_aprovado": _prop(sum(bool(r.get("escopo_aprovado")) for r in adapt), len(adapt), k_min),
        "dentro_limite_rnf07": _prop(sum(bool(r.get("dentro_limite_rnf07")) for r in adapt
                                         if "dentro_limite_rnf07" in r),
                                     sum("dentro_limite_rnf07" in r for r in adapt), k_min),
        "latencia_por_etapa": lat,
        "tokens_por_adaptacao": {"n": len(tokens), "mediana": _quantil(tokens, 0.5), "p90": _quantil(tokens, 0.9),
                                 "media": _media([float(t) for t in tokens], len(tokens), k_min)},
        "k_min_supressao": k_min,
    }
