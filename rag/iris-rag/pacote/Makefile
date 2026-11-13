# Painel de qualidade do Iris: roda as verificacoes no codigo deste repositorio e gera um painel HTML local.
# Nada sai da sua maquina (sem modelo, sem API). Na raiz do repositorio: make qualidade. Aqui: make help.
RAIZ := $(abspath $(CURDIR)/../../..)
.PHONY: help bancada registrar rastro html conferir regressao linha-de-base repetir custo revisao rastro-pipeline adversarial ablacao pipeline-tudo mapa gitnexus github tudo avaliacao juiz rotular rag-triade ataque orcamento producao ragas portoes qualidade-tudo

PY ?= python3
Q ?= Q07
# venv da bancada, fora do git (pydantic, python-docx, pymupdf, rank-bm25, numpy, pyphen, scipy; sem torch)
PYB ?= $(RAIZ)/.venv/bin/python
# provedor do LLM no pipeline: eco (determinístico, VPS) ou ollama (PC)
PROV ?= eco
# clone do repositório do grupo, SÓ LEITURA
GRUPO ?= $(RAIZ)
export PYTHONDONTWRITEBYTECODE=1

help:  ## lista os comandos
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | awk -F'\t' '{printf "  make %-12s %s\n", $$1, $$2}'

bancada: registrar html  ## registra as execuções e gera reports/bancada.html
	@echo "abra reports/bancada.html no navegador"

registrar:  ## uma linha por configuração medida, com intervalo de confiança e commit (outputs/execucoes.jsonl)
	@$(PY) bancada.py registrar

rastro:  ## caminho de uma pergunta pelo RAG no terminal (make rastro Q=Q07)
	@$(PY) bancada.py rastro $(Q)

html:  ## só gera o painel reports/bancada.html
	@$(PY) bancada.py html

conferir:  ## confere arquivos de entrada e o sha256 do chunking congelado
	@test -f chunks.jsonl || { echo "falta chunks.jsonl (ver RODAR-NO-PC.md)"; exit 1; }
	@test -f outputs/17-respostas.jsonl || echo "aviso: sem outputs/17-respostas.jsonl (rastro sem respostas)"
	@$(PY) -c "import hashlib;h=hashlib.sha256(open('chunks.jsonl','rb').read()).hexdigest()[:16];print('chunks.jsonl',h,'ok' if h=='1b517d249bef1873' else 'DIFERENTE do congelado')"

regressao:  ## compara com a linha de base e falha (código 1) se uma métrica cair
	@$(PY) bancada.py registrar >/dev/null && $(PY) bancada_checks.py regressao

linha-de-base:  ## promove o registro atual a linha de base
	@$(PY) bancada_checks.py linha-de-base

repetir:  ## reprodutibilidade da busca e dos juízes (22-repeticao.txt)
	@$(PY) bancada_checks.py repetir

custo:  ## latência, tokens e custo por peça (23-custo.txt)
	@$(PY) bancada_checks.py custo

revisao:  ## frases em que os juízes discordam -> fila de revisão humana (28-divergencias-juizes.json)
	@$(PY) bancada_checks.py divergencias

rastro-pipeline:  ## o Íris inteiro, etapa por etapa, para materiais sintéticos (26-rastro-pipeline-resumo.json)
	@cd ../bancada/pipeline && nice -n 19 $(PYB) rastro_pipeline.py --provedor $(PROV)

adversarial:  ## dados pessoais, injeção de prompt e formatos difíceis (24-adversarial.txt)
	@cd ../bancada/pipeline && nice -n 19 $(PYB) adversarial.py --provedor $(PROV)

ablacao:  ## com e sem cada peça no golden benchmark do grupo (25-ablacao.txt)
	@cd ../bancada/pipeline && nice -n 19 $(PYB) ablacao.py --provedor $(PROV)

pipeline-tudo: rastro-pipeline adversarial ablacao  ## os três (na VPS, determinístico)

mapa:  ## mapa do código do grupo: módulos, imports, testes, etapas (27-mapa-codigo.*)
	@nice -n 19 $(PY) ../bancada/mapa/mapa_codigo.py --repo $(GRUPO) --saida outputs

GREF ?= HEAD
# venv com a biblioteca RAGAS (mesma versão travada pelo grupo, 0.4.3); separado do venv da bancada
PYR ?= $(PYB)
gitnexus:  ## grafo de funções e chamadas do código do grupo com o GitNexus (29-gitnexus.json; precisa de node/npx)
	@nice -n 19 $(PY) ../bancada/mapa/gitnexus_exportar.py --repo $(GRUPO) --ref $(GREF) --saida outputs

github:  ## PRs e issues abertos do grupo (30-github.json; só leitura via gh)
	@$(PY) ../bancada/atualizar/github_estado.py --saida outputs

etapas:  ## o que cada etapa e agente faz, com exemplo real e rastro das chamadas (31-etapas.json)
	@$(PY) ../bancada/pipeline/etapas_explicadas.py --grupo $(GRUPO)

avaliacao:  ## conjunto de avaliação congelado (166 itens dos benchmarks do grupo) com nota por commit (32-avaliacao.json)
	@cd .. && nice -n 19 $(PYB) bancada/avaliacao/conjunto.py

juiz:  ## concordância dos juízes-modelo entre si e com pessoas; ficha de rotulagem em reports/ (33-juiz-calibracao.json)
	@cd .. && nice -n 19 $(PY) bancada/calibracao/calibrar.py

rotular:  ## gera a ficha HTML para rotular frases à mão (pacote/reports/calibracao/)
	@cd .. && $(PY) bancada/calibracao/rotular.py ficha

rag-triade:  ## RAG: a busca trouxe o trecho certo, a resposta só diz o que o trecho diz, cita a fonte, abstém quando deve (34-rag-triade.json)
	@cd .. && nice -n 19 $(PY) bancada/rag/triade.py --portao

ataque:  ## centenas de variações de dado pessoal, dado clínico e injeção contra o filtro real do grupo (35-ataque.json)
	@cd .. && nice -n 19 $(PYB) -W ignore bancada/ataque/gerar_e_atacar.py

orcamento: rastro-pipeline orcamento-so  ## tempo, tokens e custo por etapa contra o RNF-07 e o RNF-08 do grupo (36-orcamento.json)

orcamento-so:  ## só confere o orçamento sobre rastros que já existem (o vigia usa este, depois do rastro-pipeline)
	@cd .. && nice -n 19 $(PY) bancada/orcamento/conferir.py --grupo $(GRUPO)

producao:  ## proposta de registro em produção só com metadados: simulação sintética e testes de recusa (37-producao.json)
	@cd .. && nice -n 19 $(PYB) bancada/producao/simular.py && cd bancada/producao && $(PYB) -m unittest -q test_rastro_producao

ragas:  ## precisão do contexto com a biblioteca RAGAS do grupo (iris.eval.precisao_contexto; precisa do venv com ragas)
	@cd .. && $(PYR) bancada/rag/ragas_grupo.py --grupo $(GRUPO)

portoes:  ## lê as saídas 32 a 37 e diz aprovado, aviso ou reprovado (código 1 se reprovar)
	@$(PY) ../bancada/atualizar/portoes_novos.py

qualidade-tudo: avaliacao juiz rag-triade ataque orcamento producao portoes  ## as 6 verificações de qualidade e os portões delas

tudo: repetir custo revisao pipeline-tudo mapa gitnexus etapas qualidade-tudo bancada  ## roda todas as verificações sem modelo e gera o painel

# modo local: painel com botões para rodar cada comando, só em 127.0.0.1 (guia: ../bancada/README.md)
.PHONY: painel
PORTA ?= 8777
painel:  ## abre o painel em http://127.0.0.1:8777 com botões para rodar os comandos (só esta máquina; make painel GRUPO=...)
	@$(PY) ../bancada/local/servidor.py --porta $(PORTA) --grupo "$(GRUPO)" --py "$(PY)" --pyb "$(PYB)" --prov $(PROV)

PYL ?= $(PYB)
langgraph:  ## protótipo da arquitetura de agentes em LangGraph (laço do Auditor, pausa da professora) -> 39-langgraph.json
	@cd ../bancada/langgraph && GRUPO=$(GRUPO) PYTHONDONTWRITEBYTECODE=1 nice -n 19 $(PYL) -W ignore montar_codigo.py
	@PYTHONDONTWRITEBYTECODE=1 nice -n 19 $(PYL) -W ignore ../bancada/langgraph/grafo_iris.py
	@cd ../bancada/langgraph && PYTHONDONTWRITEBYTECODE=1 nice -n 19 $(PYL) -W ignore -m unittest test_grafo


# o que roda no repositorio do grupo sem dados privados: o pipeline inteiro com provedor eco (sem modelo),
# ataques ao filtro de dados pessoais, prova fixa, orcamento, producao, mapa e etapas
verificar: precisa-chunks rastro-pipeline adversarial ablacao mapa etapas avaliacao ataque orcamento-so producao portoes opcionais html  ## roda as verificacoes sem modelo e gera o painel
	@echo "painel em reports/bancada.html (ou: make painel)"

# abas que dependem de ferramenta externa: se faltar, avisa e segue (não derruba as outras verificações)
opcionais:
	@-$(MAKE) --no-print-directory github || echo "aviso: PRs e issues ficaram de fora (precisa do GitHub CLI logado: gh auth login)"
	@-$(MAKE) --no-print-directory langgraph || echo "aviso: a aba Arquitetura com LangGraph ficou de fora (rode make setup de novo)"

precisa-chunks:
	@test -f chunks.jsonl || { echo "falta rag/iris-rag/pacote/chunks.jsonl: rode  make setup  na raiz do repositório (monta a base de trechos)"; exit 1; }
