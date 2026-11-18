# Como Auditamos os Agentes — Observabilidade e Validação Reproduzível

A validação do sistema multiagentes da plataforma Íris combina **auditoria determinística reproduzível** (sem dependência de rede, com datasets congelados por SHA-256 e portões `exit code`) e **avaliação comportamental com LLMs** (Ollama local, Anthropic Claude e Groq).

Todos os comandos abaixo são executados a partir da pasta `iris/`.

---

## 1. Estratégia de Auditoria em Duas Camadas

| Camada | Modo / Provedores | O que garante | Onde roda |
| :--- | :--- | :--- | :--- |
| **1. Encanamento, Contratos e Guardrails** | `eco` (stub JSON determinístico) e `extractive` (regras puras) | Valida parsing JSON, filtros atômicos do RAG, conferência de citações `[T1..Tn]`, `verificar_escopo()`, cálculo de `TRCC >= 95%`, ciclo de auto-correção do Auditor, conformidade Zero-PII e orçamento RNF-07/08 sem flakiness de rede. | Local e CI (em segundos) |
| **2. Comportamento Real com Modelo (LLM)** | `ollama` (local), `anthropic`, `groq` | Mede o desempenho real dos modelos: recall das travas curriculares no Extrator, fidelidade das intervenções no Estrategista, adesão ao escopo sem queda para reserva no Adaptador, precisão/revocação do Juiz Auditor e latência/tokens reais contra o RNF-07 e o RNF-08. | Máquina local / Bancada |

---

## 2. Matriz de Validação por Agente

Cada agente é auditado pelos seus contratos de entrada/saída, guardrails determinísticos e códigos explícitos de `motivo_fallback`:

| Agente | Módulos Principais | O que valida se está "certo" | Códigos de `motivo_fallback` observáveis |
| :--- | :--- | :--- | :--- |
| **1. Extrator Curricular (`#17`)** | `backend/src/iris/agents/curriculum_extractor.py` | Recall das travas contra `golden_benchmark.json` ($\ge 95\%$), `json_valido_direto`, normalização do verbo BNCC ao infinitivo e preservação de `trava_manual_docente`. | `provedor_sem_modelo`, `falha_llm:<Tipo>` |
| **2. Estrategista RAG (`#16`)** | `backend/src/iris/agents/strategist_agent.py` | Filtro pré-prompt pela barreira (`trechos_fora_do_filtro`), zero citações `[Tn]` inexistentes ou de outra característica (`citacoes_validas`), limite $\le 40$ palavras por intervenção e trava anti-cópia literal ($\ge 12$ palavras). | `sem_evidencia`, `provedor_sem_modelo`, `nenhuma_intervencao_aprovada`, `falha_llm:<Tipo>` |
| **3. Adaptador Pedagógico (`#18`)** | `backend/src/iris/agents/adapter_agent.py` · `iris/eval/escopo.py` | Aprovação em `verificar_escopo()` (contagem de palavras, ordem via LCS, estrutura e conceitos da trava), ações do `conferente_por_regra` e entrega segura por `_saida_de_reserva`. | `provedor_sem_modelo`, `regra_comandos_multiplos`, `escopo_reprovado`, `conferente_palavra_perdida`, `falha_llm:<Tipo>` |
| **4. Auditor de Integridade (`#19`)** | `backend/src/iris/agents/auditor.py` | `TRCC >= 0.95`, 100% dos `termos_tecnicos_intocaveis`, detecção de gabarito/cálculo resolvido/alternativas eliminadas, julgamento LLM restrito a `trechos_novos` com citação literal obrigatória e *Circuit Breaker* em `max_tentativas=3` (`requer_revisao_humana`). | Falha fechada (`aprovado=False` após 2 JSONs inválidos do juiz ou ciclo esgotado) |

> **Observação sobre `comandos_por_regra` e `conferente_por_regra` no Adaptador:**  
> Por padrão, o `AdapterAgent` ativa `comandos_por_regra=True` (aplica decomposição determinística em comandos múltiplos, com `motivo_fallback="regra_comandos_multiplos"`) e `conferente_por_regra=True` (solicita 1 regeneração se o LLM perder palavras em características sem regra explícita, e devolve o original com `motivo_fallback="conferente_palavra_perdida"` se perder de novo). Nos avaliadores de modelo (`adaptador_com_modelo`, `rastro_pipeline` e `multiagentes_ciclo`), essas flags são controláveis para distinguir o comportamento puro do LLM da malha determinística.

---

## 3. Comandos Reproduzíveis (Makefile e CLI)

| Objetivo | Comando | Artefatos Gerados / Saída |
| :--- | :--- | :--- |
| **Ciclo E2E dos 4 agentes (Golden Benchmark)** | `make eval-agentes` *(padrão `PROV=eco`; aceita `PROV=ollama\|anthropic\|groq LIMITE=N`)* | `reports/multiagentes_ciclo.json` e `reports/multiagentes_ciclo.md` |
| **Painel Completo da Bancada + 6 Portões** | `make qualidade` e `make qualidade-painel` | `rag/iris-rag/pacote/outputs/24..39` e painel em `http://127.0.0.1:8777` |
| **Benchmark + Analytics do Extrator (`#17`)** | `make extrator-bench` e `make extrator-analytics` | `reports/extractor_telemetry.jsonl` + tabela por disciplina e faixa etária |
| **Isolamento de Escopo do Adaptador (`#18`)** | `make eval-adaptador` | `reports/adaptador_com_modelo.{json,md}` (90 chamadas: 30 questões × 3 níveis) |
| **Latência Extrator + Adaptador vs RNF-07** | `make eval-ciclo` | `reports/adaptador_ciclo.{json,md,png}` (90 ciclos contra limites 15s / 40s) |
| **Calibração do Juiz LLM do Auditor (`#19`)** | `make eval-juiz PROV=ollama` *(ou `PROV=groq`)* | Precisão, recall e acurácia de resolução indevida e intrusão |
| **Demonstração Clínica de Colaboração + Retry** | `make multiagentes` *(ou `make multiagentes-menu`)* | Execução passo a passo no terminal com simulação de auto-correção |
| **Auditoria de Conformidade Zero-Database** | `python3 scripts/audit_zero_database.py` | Verifica ausência de bancos/persistência proibida em todo o código |
| **Suíte Automatizada de Testes** | `make test` | Bateria `backend/tests/` (contratos, agentes, LangGraph, rotas e temas) |

Execuções avançadas direto pelo módulo Python:

```bash
cd iris
# Ciclo completo dos 4 agentes com amostra controlada e modelo local Ollama
PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 -m iris.eval.multiagentes_ciclo --provider ollama --limite 5

# Rastro etapa por etapa de materiais DOCX/PDF/TXT com os 4 agentes reais
PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 rag/iris-rag/bancada/pipeline/rastro_pipeline.py --provedor eco

# Grafo LangGraph dos agentes (testando ciclo do Auditor e pausa para revisão docente)
PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 -m unittest discover -s rag/iris-rag/bancada/langgraph -p "test_grafo.py"
```

---

## 4. Conjuntos Congelados e Portões de Qualidade (`portoes_novos.py`)

Os avaliadores operam sobre bases versionadas no repositório:

1. **`data/golden_benchmark.json`:** 30 questões escolares multi-disciplinares com travas curriculares de referência.
2. **`rag/iris-rag/bancada/avaliacao/conjunto-v1.jsonl`:** prova fixa de **166 questões** lacrada por hash SHA-256 em `conjunto-v1.manifesto.json` para comparação justa entre commits.
3. **`data/benchmarks/juiz_auditor_v1.json`:** 18 minutas sintéticas rotuladas para calibrar o juiz LLM do Auditor contra falsos positivos e falsos negativos.
4. **`rag/iris-rag/bancada/pipeline/casos_adversariais.jsonl`:** bateria com casos sintéticos de PII, injeção de prompt e formatos corrompidos.

Ao executar `make qualidade`, os 6 portões em `rag/iris-rag/bancada/atualizar/portoes_novos.py` validam automaticamente (retornando código de saída `1` se houver regressão crítica):

- **Conjunto de avaliação (`32-avaliacao.json`):** lacre SHA-256 intacto, zero falhas de pipeline, $\text{IC95}_{\text{inf}}(\text{TRCC}) \ge 0.95$ e aprovação do laudo de escopo.
- **Juiz calibrado (`33-juiz-calibracao.json`):** concordância (Kappa) e erro de aprovação indevida contra rotulagem humana.
- **Tríade do RAG (`34-rag-triade.json`):** busca, fidelidade, citação e abstenção na configuração `v1`.
- **Ataque em massa PII (`35-ataque.json`):** ausência de novos padrões de vazamento no gateway local.
- **Orçamento RNF-07 / RNF-08 (`36-orcamento.json`):** máximo de 3 chamadas de modelo por questão, máximo de 15 por atividade de 5 questões e limite de 8.000 tokens da cadeia.
- **Rastro de produção Zero-PII (`37-producao.json`):** confirmação de que apenas metadados estruturados (sem texto do aluno nem PII) entram no log operacional.
- **Logs operacionais Zero-Retention em produção (`#37`):** `backend/src/iris/security/operational_logger.py` (`ZeroPiiLogFilter`, `ZeroPiiLogFormatter`, `sentinel_context`, `log_http_operational_event` e `log_agent_operational_event`) garante em runtime e em memória que apenas `status_code`, `latency_s`, `total_tokens`, `trcc_scores` e códigos fechados sejam emitidos — validado continuamente por `backend/tests/test_auditoria_logs_zero_pii.py`.

---

## 5. Onde Inspecionar Visualmente

- **Aplicação Docente (`/etapa-4` em `http://localhost:3000`):** ao executar o Sistema Multiagentes, exibe os 4 cards individuais (`Extrator`, `Estrategista RAG`, `Adaptador` e `Auditor`), o histórico de tentativas de auto-correção e os motivos de fallback.
- **Playground Backend (`http://127.0.0.1:8000`):**
  - Aba **Arquitetura (LangGraph):** mostra o fluxograma executável dos 4 agentes, os 5 cenários de teste (incluindo falha/retomada e reprovação pelo Auditor) e o resumo de como os auditamos.
  - Menu recolhível **Verificações de qualidade:** consolida as 16 telas geradas pela bancada (`Pipeline inteiro`, `Conjunto de avaliação`, `Orçamento RNF-07`, `Segurança e ablação`, etc.).
