# Perfil Pedagógico Portátil (Histórias 3.1.1 / #26 e 3.1.3 / #28)

Schema oficial em `backend/src/iris/schemas/portable_profile.py`. Implementa RF-15, RNF-01 e RNF-03: o perfil guarda **apenas** barreiras funcionais observadas em sala e o histórico de
estratégias didáticas. CID, laudos, diagnósticos formais e medicação são rejeitados.

## Criação com identificador anônimo (#26)

```python
from iris.schemas.portable_profile import criar_perfil

perfil = criar_perfil(["atencao_sustentada_textos_longos"], ids_validos=ids_do_catalogo)
perfil.codigo_anonimo      # "aluno-8f7a2c1b": UUID4 aleatório, sem nenhuma entrada do usuário
perfil.criado_em           # data/hora UTC
perfil.para_json()         # dict pronto para o navegador baixar
```

- O código vem só de `gerar_codigo_anonimo()` (que não recebe dados do estudante). O schema aceita **apenas** o formato
  `aluno-` + 8 a 32 hex: um nome digitado no lugar do código é rejeitado.
- Com 8 hex, a chance de colisão chega a ~1% perto de 9 mil perfis. Como não há banco para checar unicidade, use
  `gerar_codigo_anonimo(16)` se isso importar.
- **Nada é persistido.** O módulo não importa banco, rede nem escreve arquivo; `tests/test_perfil_portatil.py` verifica isso
  por inspeção de código (AST) e por execução (bloqueando escrita em disco e conexões).
- Quem entrega o JSON ao docente (rota ou frontend) não deve guardar cópia no servidor.

## Uso da validação

```python
from iris.schemas.portable_profile import validar_perfil, PerfilInvalidoError

try:
    perfil = validar_perfil(conteudo_do_json)        # str, bytes ou dict (ex.: reimportação)
except PerfilInvalidoError as e:
    e.codigo                         # CLINICAL_DATA_BLOCKED | INVALID_STRUCTURE | INVALID_JSON
    e.to_dict()                      # {"detail", "code", "field", "violacoes": [{campo, categoria, orientacao, trecho}]}
```

O schema `PerfilPedagogico` também pode ser usado direto (`model_validate`); nesse caso o erro vem como
`pydantic.ValidationError`.

## Campos (RF-15)

| Campo | Conteúdo |
|---|---|
| `versao_schema` | `"1.0"` |
| `codigo_anonimo` | `aluno-` + 8 a 32 hex minúsculos |
| `criado_em` | data/hora com fuso (UTC por padrão) |
| `caracteristicas_selecionadas[]` | ids do catálogo, sem repetição |
| `barreiras_observadas[]` | `id_caracteristica` (do catálogo) + `observacao` opcional |
| `historico_estrategias[]` | `estrategia`, `resultado` (`eficaz`/`ineficaz`), `id_caracteristica` e `observacao` opcionais |
| `historico_intervencoes[]` | (opcional, #27) `estrategia`, `id_caracteristica` (obrigatória, deve estar no perfil), `eficacia` (`alta`/`media`/`baixa`), `observacao` opcional e `registrado_em` (UTC) |
| `anotacoes_pedagogicas[]` | textos livres (até 1000 caracteres) |

Qualquer campo não declarado é rejeitado (`extra="forbid"`).

## O que é bloqueado

Chaves **e** valores são varridos recursivamente.

| Categoria | Exemplos |
|---|---|
| `cid` | `CID F90.0`, `F84`, `6A05`, "Classificação Internacional de Doenças" |
| `laudo` | laudo, atestado médico, relatório clínico, prontuário, receita médica, neuropsicológico |
| `diagnostico` | "diagnóstico médico/clínico", "tem diagnóstico", diagnosticado, TDAH e T.D.A.H., TEA/TOC (siglas em maiúsculas), autismo, "no espectro", dislexia, "transtorno de/do…", síndrome |
| `medicacao` | nomes de medicamentos, "toma Concerta", "medicação", "remédio", doses (`10 mg`, gotas, comprimidos), psiquiatra/neurologista |

Não são bloqueados: "avaliação diagnóstica", "diagnóstico pedagógico", "diagnóstico inicial da turma",
"a troca de sala causou transtorno", "ele concerta os erros", "garrafa de 500 ml", "toc toc", códigos como
`Q10`, "A4", "ambiente estimulante", "receita de bolo". Como *nome de campo*, `diagnostico`/`transtorno` são sempre bloqueados.

## Privacidade

`str(exc)` **não** repete o trecho digitado (pode ir para logs). O trecho só sai em
`to_dict(incluir_trecho=True)`, para exibir ao docente na interface. Na mensagem e em `to_dict(incluir_trecho=False)`,
nomes de campo não declarados no schema aparecem como `<campo não declarado>`, porque o próprio nome pode ser o dado
clínico (ex.: `laudo_tdah`).

## Limites conhecidos

- Lista finita de termos e medicamentos; nomes novos exigem atualizar as constantes em `schemas/portable_profile.py`.
- `F\d{2}` (ex.: `F10`) é tratado como CID; um código de exercício igual a esse seria um falso positivo.
- Deficiências sensoriais/físicas (ex.: "baixa visão") não são bloqueadas por serem informação de acessibilidade.
- A validação não detecta dados pessoais (nome do aluno, CPF) em texto livre; a exportação pelo servidor aplica o
  `security/pii_scrubber.py`, que não reconhece nome de pessoa em texto corrido.
- Termos clínicos dentro de identificadores com sublinhado (`tdah_formal`) também são detectados.
- `historico_estrategias` (#28, `eficaz`/`ineficaz`) continua válido e não foi alterado. O registro de eficácia por
  característica da 3.1.2 (#27) fica em `historico_intervencoes`, com três níveis e data.
- O perfil é criado e baixado no navegador, pelo painel da etapa 2 (`frontend/src/services/portableProfile.ts`, que espelha
  este schema). A única rota de API do perfil é a de exportação, descrita abaixo; `criar_perfil` ainda não é chamado pelo
  servidor.

## Exportação (.json e .pdf)
O docente baixa o perfil por dois caminhos (História 3.2.1, RF-15, RNF-01):

| Formato | Onde é gerado | Uso |
|---|---|---|
| `.json` | no navegador (`portableProfile.ts`), funciona offline | reuso no sistema; segue o schema oficial |
| `.pdf` | no servidor, por `POST /api/v1/perfil/exportar?formato=pdf` | relatório síntese para anexar ao PDI |

`POST /api/v1/perfil/exportar?formato=json|pdf` recebe o perfil no corpo e passa por `validar_perfil`
(schema oficial + bloqueio de laudo, CID, diagnóstico e medicação). Perfil inválido devolve `422` e nunca
gera arquivo; a resposta de erro não repete o trecho digitado.

**Dado pessoal em texto livre.** Antes de virar arquivo, anotações, observações e estratégias passam por
`security/pii_scrubber.sanitize_pii`: CPF, telefone, e-mail e matrícula saem como marcadores (`[CPF]`, `[TELEFONE]`,
`[EMAIL]`, `[IDENTIFICADOR]`). Nome de pessoa em texto corrido não é detectado; o rodapé do PDF avisa o docente para
revisar antes de compartilhar. O `.json` gerado no navegador não passa por essa etapa.

**Sem sessão no servidor.** Não existe sessão em memória para destruir: a rota recebe o perfil, monta o
arquivo em memória, devolve os bytes e esquece. Não usa disco, banco, cache nem variável global, e a resposta
leva `Cache-Control: no-store`. Por isso encerrar o servidor não faz o docente perder o que já baixou.
Os testes provam isso (sem importar bibliotecas de persistência, sem escrever em disco, sem rede e sem
alterar o estado do módulo durante a exportação).

O PDF é montado com PyMuPDF (já dependência do projeto). Traz código anônimo, data, as características com
nome e descrição do catálogo oficial e, se existirem, barreiras, estratégias e anotações.

## Histórico de eficácia das intervenções (História 3.1.2, Issue #27)

Com o perfil carregado, o docente registra se uma estratégia funcionou para uma característica do perfil: escolhe a
característica, descreve a estratégia, marca a eficácia (**alta**, **média** ou **baixa**) e, se quiser, escreve uma
observação pedagógica. O registro é anexado ao `historico_intervencoes`.

- **Ordem:** o histórico é mantido em ordem cronológica (do mais antigo ao mais recente). Na tela, os mais recentes
  aparecem primeiro. Registros do mesmo instante mantêm a ordem de entrada. Um perfil importado fora de ordem é reordenado.
- **Eficácia:** o valor guardado é sempre `alta`, `media` ou `baixa`. A API aceita também `média`/`Média`.
- **Regras:** a característica precisa estar no perfil; estratégia de 3 a 300 caracteres; observação até 500; no
  máximo 200 registros; `registrado_em` é preenchido pelo servidor.
- **Clínico (RNF-03):** estratégia e observação passam pelo mesmo bloqueio de laudo, CID, diagnóstico e medicação.
- **Privacidade (RNF-01):** `POST /api/v1/perfil/intervencoes` recebe `{perfil, intervencao}` e devolve o perfil com o
  registro e um `resumo_eficacia` por característica. O servidor não guarda nada (`Cache-Control: no-store`). O perfil
  atualizado fica no navegador (memória e `localStorage`), e o `.json` e o `.pdf` exportados trazem o histórico.
- **Compatibilidade:** perfis anteriores, sem o campo, continuam válidos; o campo só aparece após o primeiro registro.

```json
{"perfil": {"...": "..."}, "intervencao": {"estrategia": "Fragmentação em checklist",
 "id_caracteristica": "atencao_sustentada_textos_longos", "eficacia": "alta", "observacao": "Terminou a prova."}}
```

## Importação e restauração da sessão (História 3.2.2, Issue #31)

No início do fluxo (Etapa 1), o professor importa o `.json` recebido da coordenação ou do AEE. A plataforma valida o
arquivo e pré-marca as características e o nível de suporte nas Etapas 2 e 3. O docente confere, pode alterar tudo e
só então confirma: a importação nunca avança o fluxo sozinha.

**Como funciona**
1. O navegador lê o arquivo (só `.json`, até 1 MB) e envia o **texto** a `POST /api/v1/perfil/importar`, no corpo
   `{"arquivo": "<texto>"}`. O servidor valida pelo schema oficial (`validar_perfil`, o mesmo da exportação) e devolve
   `{perfil, resumo_eficacia}`. Não guarda nada e responde com `Cache-Control: no-store`.
2. Se o servidor estiver fora do ar, o navegador valida localmente o mesmo schema (chaves, versão, código anônimo,
   formato dos identificadores e chaves pessoais ou clínicas). Nesse caminho não há varredura do texto livre das
   observações; ela só existe na validação do servidor.
3. A prévia mostra o que será restaurado. Só ao clicar em **Aplicar ao fluxo** a sessão da aba recebe o resultado.
   Se já havia seleção ou calibração na sessão, a tela avisa que serão substituídas.
4. A Etapa 2 abre com as características pré-marcadas (as que não constam no catálogo ativo são ignoradas, com aviso)
   e a Etapa 3 abre com o nível sugerido, quando houver. **Remover perfil importado** desfaz a restauração.

**Erros (HTTP 422, ou 413 para arquivo acima de 1 MB)**

| `code` | Quando |
|---|---|
| `INVALID_JSON` | arquivo truncado ou que não é JSON |
| `INVALID_STRUCTURE` | JSON fora do schema (campo extra, versão, código anônimo, característica repetida…) |
| `CLINICAL_DATA_BLOCKED` | laudo, CID, diagnóstico ou medicação no perfil (a resposta não repete o trecho) |
| `EMPTY_FILE` | arquivo vazio |
| `FILE_TOO_LARGE` | mais de 1 MB |

A mensagem de cada erro aparece em linguagem simples e a aplicação continua utilizável: o professor pode seguir sem importar.

**Regra do nível de andaime.** O perfil não guarda um campo de nível; guarda o histórico de eficácia das estratégias.
Por isso a sugestão é derivada dele, de forma conservadora:
- só contam registros com eficácia **alta**;
- o nível é reconhecido apenas quando a estratégia o **cita** (`nível 2`, `nível leve`, `andaime intensivo`…);
- sugere-se o nível mais citado; havendo **empate**, ou nenhuma menção, não se sugere nenhum e a Etapa 3 segue no padrão;
- a tela diz por que o nível foi sugerido, e o docente pode trocá-lo.

**O que fica na sessão da aba** (`sessionStorage`, chave `iris_session_perfil_importado_v1`): código anônimo,
identificadores das características, as que têm eficácia alta, o nível sugerido e a frase de justificativa. Nunca o
arquivo, as estratégias nem as observações. Não se usa `localStorage` nem IndexedDB para a importação.
