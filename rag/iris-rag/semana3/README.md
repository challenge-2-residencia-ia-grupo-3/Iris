# Semana 3 – LLM x RAG

Estudo comparativo do Segundo Desafio, entrega de 13/11/2026: o modelo de linguagem sozinho (A), a busca sem
modelo (B), a geração aumentada por recuperação com modelo (C) e o produto adaptando questões com e sem
recuperação (D). O relatório está em [`docs/rag/semana3/relatorio.md`](../../../docs/rag/semana3/relatorio.md)
e em PDF na mesma pasta.

O estudo foi conduzido em repositório de trabalho privado e trazido para cá ao final. O código do produto
avaliado é o deste repositório no commit `65e1f09`.

## Como reproduzir

Nesta pasta, com Python 3.10 ou mais novo e sem instalar nada:

```bash
python reproduzir.py
```

O comando refaz, a partir dos vereditos do juiz, as métricas por condição, as diferenças pareadas, a regra de
decisão, as hipóteses, a concordância do juiz e a rodada de 50 candidatos. Depois compara cada saída nova com a
versionada e avisa se algum número mudou. Leva menos de um minuto e deixa os arquivos como estavam.

Cada tabela do relatório cita, na linha "Fonte", a saída de onde os números vieram (por exemplo, a Tabela 3 vem
de `saidas/juiz_metricas.txt`).

Para montar o PDF a partir do Markdown: `python relatorio/montar_relatorio.py` (precisa de `mistune`, `pymupdf`
e do Google Chrome).

## Refazer a geração

As respostas dos modelos e os trechos da busca não estão no repositório (ver a última seção). Para gerá-los de
novo é preciso a base indexada (`rag/README.md`), o Ollama com `llama3.1:8b` e uma GPU. A partir de `rag/iris-rag`:

```bash
python semana3/busca.py                                        # busca nas 40 perguntas; grava trechos e prompts
python semana3/teste_b.py                                      # teste B
python semana3/gerar_ac.py --modelo llama3.1-8b --testes A,C   # testes A e C, 3 repetições
python semana3/metricas.py                                     # métricas por código
python semana3/pacotes_juiz.py                                 # lotes cegos para o juiz
```

Com esses arquivos no lugar, `python reproduzir.py --tudo` confere também as análises que dependem deles
(precisa do `scipy`). Sem eles, os scripts param com uma mensagem dizendo o que falta.

Uma geração nova não repete os números exatos do relatório: o Llama variou entre repetições mesmo com
temperatura 0, as respostas novas precisam de um novo julgamento, e o juiz não tem temperatura fixa. O que se
espera reproduzir é a ordem de grandeza e a conclusão. Os números exatos saem dos vereditos guardados.

## Conteúdo

| Caminho | O que é |
|---|---|
| `PREREG.md` | pré-registro: perguntas, condições, métricas, hipóteses e regra de decisão, escritos antes de rodar; todos os desvios, datados |
| `comum.py`, `busca.py`, `gerar_ac.py`, `teste_b.py`, `teste_d.py`, `rodar_no_pc.py` | geração dos testes A, B, C e D |
| `metricas.py` | métricas calculadas por código (`saidas/metricas.txt`) |
| `pacotes_juiz.py`, `juiz/INSTRUCOES-JUIZ.md`, `juiz/chave.json`, `juiz/vereditos/` | lotes cegos, rubrica, chave e vereditos do juiz (Claude Opus) |
| `analise_juiz.py`, `concordancia_rejulgamento.py` | métricas do juiz, regra de decisão, hipóteses e estabilidade do juiz |
| `rodada_r50.py`, `saidas_r50/` | rodada complementar com reordenação sobre 50 candidatos |
| `rodada_fora.py`, `saidas_fora/`, `../gabarito/fora_da_base_v1.json` | rodada complementar com 25 perguntas sem resposta na base e limiar de escore |
| `analise_complementar.py` | busca certa x errada, correção de Holm e menor diferença detectável |
| `d_diagnostico.py` | diagnóstico da saída de reserva do teste D |
| `reproduzir.py` | refaz a análise e confere com as saídas versionadas |
| `relatorio/` | fonte do relatório e scripts que montam o PDF e as figuras |

## O que não está aqui, e por quê

- **Respostas geradas, trechos recuperados, prompts gravados e lotes do juiz.** Trazem texto integral de
  documentos sem licença aberta (ver `../textos_nao_distribuidos.txt`). Estão listados no `.gitignore` desta
  pasta. Sem eles, os scripts de análise que leem as respostas não reproduzem os números; as saídas
  agregadas (`saidas*/*.txt` e `*.json`) e os vereditos estão versionados.
- **A bancada de testes** (`bancada/pipeline`), usada por `teste_d.py` e `d_diagnostico.py` para executar o
  Agente Adaptador com rastro. Ela está no repositório de trabalho. Esses dois scripts ficam aqui para leitura.
- **Conferência humana.** O juiz não foi validado por pessoa e os conjuntos de referência não foram revisados;
  as duas pendências estão declaradas na seção 9 do relatório.

Em relação ao repositório de trabalho, três linhas com caminhos de máquina foram trocadas por caminhos
relativos (`busca.py`, `teste_b.py`, `comum.py`) e os caminhos citados no relatório apontam para este repositório.
