# Arnês de ponta a ponta do Íris (bancada/pipeline)

Três comandos que rodam o **código do grupo** (clone só leitura, commit `65e1f09`) sem alterar nenhum arquivo
dele. As funções do grupo entram pelo `sys.path` e são envolvidas por wrappers em tempo de execução
(`trace.py`); nenhum `.pyc` é gravado no clone e o `chunks.jsonl` vem do pacote congelado deste repositório
(sha16 `1b517d249bef1873`), não é gerado dentro do clone.

| comando | pergunta que responde | saída versionável | saída completa (fora do git) |
|---|---|---|---|
| `rastro_pipeline.py` | o que cada etapa recebeu, devolveu, quanto demorou e onde quebrou, para um material | `pacote/outputs/26-rastro-pipeline-resumo.json` | `pacote/reports/pipeline/<run_id>.jsonl` |
| `adversarial.py` | o que o pipeline faz com dado pessoal, injeção de prompt e formato difícil | `pacote/outputs/24-adversarial.txt` e `.jsonl` | `pacote/reports/pipeline/adv-*.jsonl` |
| `ablacao.py` | quanto cada peça (Extrator, RAG, laudo de escopo, modelo) muda as métricas do grupo no Golden Benchmark | `pacote/outputs/25-ablacao.txt` e `.jsonl` | `pacote/reports/pipeline/ablacao-*/` |

Arquivos de apoio: `trace.py` (ambiente, esquema do rastro, wrappers, provedores), `gerar_casos.py` (escreve
`casos_adversariais.jsonl`, 41 casos sintéticos), e os scripts de cada verificação.

## Etapas rastreadas (o que existe no commit 65e1f09)

| ordem | etapa | função do grupo |
|---|---|---|
| 1 | upload_tamanho | `iris/schemas/materials.py:validate_file_size_limit` |
| 2 | extracao_documento | `iris/parsers/document_extractor.py:extract_text_from_file` (.txt/.pdf/.docx) |
| 3 | filtro_pii | `iris/security/pii_scrubber.py:sanitize_pii` |
| 4 | validacao_conteudo | `iris/schemas/materials.py:validate_material_content` (50 a 100.000 caracteres) |
| 5 | decomposicao_estrutural | `iris/parsers/structural_decomposer.py:decompose_material` |
| 6 | organizacao_texto_corrido | `iris/parsers/prose_organizer.py:organize_prose_structure` (chamada de dentro da 5) |
| 7 | selecao_caracteristicas | `iris/api/routes/catalogs.py:select_surgical_characteristics_service` (catálogo TDAH, 10 características) |
| 8 | perfil_pedagogico | `iris/schemas/profile.py:validar_perfil` (perfil sintético; bloqueia CID/laudo) |
| por questão | extrator_curricular | `iris/agents/curriculum_extractor.py:CurriculumExtractorAgent.extract_with_telemetry` |
| por questão | busca_rag | `iris/rag/bridge.py:buscar_por_caracteristica_atomica` (forçado `metodo="bm25"`) |
| por questão | contexto_rag | `iris/rag/contexto.py:montar_contexto_estrategista` |
| por questão | agente_estrategista | **não implementada no commit 65e1f09**; o arnês põe no lugar `diretiva_substituta_arnes` (cliente de LLM do grupo + `gerar.INSTRUCOES` do pacote RAG do grupo) |
| por questão | conferencia_citacoes | `iris/rag/contexto.py:conferir_citacoes` |
| por questão | agente_adaptador | `iris/agents/adapter_agent.py:AdapterAgent.adapt` |
| por questão | laudo_isolamento_escopo | `iris/eval/escopo.py:verificar_escopo` (chamado de dentro do Adaptador) |
| por questão | saida_de_reserva | `AdapterAgent._saida_de_reserva` (só aparece quando o Adaptador cai na reserva) |
| por questão | agente_auditor | **não implementada no commit 65e1f09** (História 2.1.4, issue #19) |
| por questão | ciclo_rnf07 | `iris/agents/adapter_agent.py:resumir_ciclo` |

O grupo ainda não liga a decomposição aos agentes (não há orquestrador): a ligação "cada questão decomposta
vai para Extrator -> RAG -> Adaptador" é do arnês. Sem questões detectadas, o texto inteiro vira uma questão.

## Provedores

| provedor | onde | o que faz |
|---|---|---|
| `eco` (padrão) | VPS | stub determinístico deste arnês: responde JSON válido ao Extrator e ao Adaptador (andaime por regras do grupo), para exercitar o caminho "com modelo" (parse, laudo, telemetria). Não mede qualidade. |
| `extractive` | VPS | `ExtractiveFallbackLLMProvider` do grupo: Extrator e Adaptador pulam o modelo e usam as regras de reserva |
| `ollama` | PC | `OllamaLLMProvider` do grupo, modelo padrão `llama3:latest` |

`groq` é recusado de propósito (nada sai da máquina). O RAG roda só com `bm25` (não carrega Qwen3, torch nem banco).

## Rodar na VPS (determinístico)

```bash
V=../../../../.venv/bin/python   # o .venv do projeto (make setup)
cd challenges/challenge-02-qualidade-de-vida/iris-rag/bancada/pipeline
nice -n 19 $V rastro_pipeline.py            # 3 materiais sintéticos (docx, pdf, txt), ~5 s
nice -n 19 $V adversarial.py                # 41 casos (21 PII, 7 injeção, 13 formato), ~5 s
nice -n 19 $V ablacao.py                    # 7 configurações x 30 questões, nível 2, ~9 s, ~100 MB de RAM
```

Opções úteis: `--provedor extractive`, `--nivel 1|3`, `adversarial.py --so-pii`, `ablacao.py --limite 5 --configs completo,sem_rag`.
Variáveis: `IRIS_GRUPO` (caminho do clone do grupo), `IRIS_BANCADA_CHUNKS` (outro `chunks.jsonl`).
O venv foi criado com `uv venv --python 3.11 .../iris-bancada-venv` e
`uv pip install pydantic python-docx pymupdf rank-bm25 numpy pyphen scipy`.

## Rodar no PC (Ollama)

Mesmos comandos com `--provedor ollama` (Ollama ligado nesta máquina).

## Limites que valem para os três

- Com `eco`/`extractive` os números medem o encanamento, não um modelo. Em particular, a injeção de prompt só é
  testada de verdade com `--provedor ollama`.
- O stub `eco` ignora a diretiva do RAG: na VPS, `completo` e `sem_rag` dão o mesmo resultado por construção.
- Golden Benchmark do grupo está como `rascunho` (sem revisão pedagógica); 30 questões, 1 questão = 3,3 pontos.
- O rastro completo guarda trechos do RAG (alguns de licença restrita): fica em `pacote/reports/`, que o git ignora.
