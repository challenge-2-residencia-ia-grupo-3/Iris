# Agente Auditor (História 2.1.4, #19)

Valida a minuta de questão adaptada antes de ela chegar ao professor (RF-12, RNF-04, RNF-05).

## Uso

```python
from iris.agents.auditor import AgenteAuditor, caracteristicas_nao_selecionadas
from iris.core.llm_client import get_llm_client

auditor = AgenteAuditor(get_llm_client())            # juiz = qualquer objeto com .generate(prompt)
nao_sel = caracteristicas_nao_selecionadas(ids_do_professor)   # lê rag/catalogs/

# auditoria de uma minuta
r = auditor.auditar(original, minuta, travas, nao_sel)
r.aprovado, r.trcc.trcc, r.resolucao_indevida, r.intrusoes, r.motivos

# ciclo de auto-correção; `adaptar` é o Agente Adaptador (#18)
rel = auditor.executar_ciclo(original, travas, adaptar, nao_sel, max_tentativas=3)
rel.aprovado, rel.texto_final, rel.requer_revisao_humana, rel.tentativas
```

`adaptar(feedback, minuta_anterior) -> str`: na primeira chamada ambos são `None`.

## Integração com o Extrator (#17)

O argumento `travas` aceita uma lista de conceitos **ou** o `CurriculumInvariants` do Extrator:

```python
inv = get_curriculum_extractor().extract(enunciado, disciplina="Matemática")
rel = auditor.executar_ciclo(enunciado, inv, adaptar, nao_sel)
```

- `conceitos_obrigatorios` vira a trava da TRCC (o conceito genérico `conteudo_curricular` é ignorado);
- `alerta_anti_muleta` entra no prompt do juiz como o que não pode ser entregue;
- `termos_tecnicos_intocaveis` ausentes reprovam, sem a tolerância de 5% da TRCC.

## Regras

| Verificação | Como | Reprova quando |
|---|---|---|
| TRCC | `iris.eval.trcc.avaliar_trcc` (determinístico) | < 95%; trava vazia também reprova |
| Termos intocáveis | `avaliar_trcc` sobre `termos_tecnicos_intocaveis` | qualquer termo ausente |
| Resolução indevida | regras + juiz LLM | marca de gabarito nova, cálculo já resolvido (`12 × 25 = 300`), alternativas reduzidas a ≤ 1 (contadas pelo conteúdo, não pela letra: renumerar `a)` como `1.` não é eliminar), ou juiz aponta |
| Intrusão | juiz LLM, só com características NÃO selecionadas | juiz aponta (ou só avisa, com `intrusao_bloqueia=False`) |
| Juiz inválido | JSON inválido após 2 tentativas (a 2ª com temperatura 0,3 e o dobro de tokens) | sempre reprova (falha fechada) |

Ciclo esgotado nunca é aprovado: devolve a última minuta com `requer_revisao_humana=True`.

## Como o juiz é protegido de alucinar

1. **Diff determinístico** (`trechos_novos`): o juiz só vê os trechos que a minuta acrescentou ou alterou. Minuta
   sem acréscimos nem chama o juiz.
2. **Citação literal obrigatória**: toda acusação (resolução ou intrusão) precisa citar um desses trechos.
   Acusação sem citação é descartada e registrada em `motivos`.

## Medindo o juiz

```bash
PYTHONPATH=backend/src python -m iris.eval.juiz_auditor --provider groq
PYTHONPATH=backend/src python -m iris.eval.juiz_auditor --provider ollama --model llama3.1:8b
```

Roda 18 minutas rotuladas (`data/benchmarks/juiz_auditor_v1.json`) e imprime JSON inválido, precisão/recall da
resolução e da intrusão, latência e as minutas em que o juiz divergiu.

### Resultado medido (llama3.1:8b, Ollama local)

| Métrica | Valor |
|---|---|
| JSON inválido | 1/18 (antes da correção da nova tentativa) |
| Resolução: precisão / recall | 1,0 / 0,4 |
| Intrusão por minuta: precisão / recall | 0,36 / 0,8 |
| Intrusão por característica: precisão / recall | 0,125 / 0,4 |
| Latência média | 12,5 s por minuta |

Conclusão: o 8b local **não é confiável** como juiz de intrusão (acusa `sobrecarga_memoria_trabalho_comandos_multiplos`
quase sempre) e perde dicas de resposta em texto. Não foi medido com um modelo maior (Groq 70B, Qwen). Enquanto não
houver juiz validado, considerar `AgenteAuditor(juiz, intrusao_bloqueia=False)`.

## Limites conhecidos

- O conjunto de avaliação é pequeno (18 minutas sintéticas, 5 questões) e é só um termômetro.
- `retencao_dados_intermediarios`, `sobrecarga_memoria_trabalho_comandos_multiplos` e `organizacao_sequencial`
  produzem adaptações parecidas ("dividir em etapas"); nenhum juiz as distingue de forma confiável.
- TRCC não lematiza: flexões devem ser listadas como alternativas (`a|b`) na trava.
- Ainda não integrado ao Agente Adaptador (#18): o ciclo recebe uma função `adaptar(feedback, minuta_anterior)`.