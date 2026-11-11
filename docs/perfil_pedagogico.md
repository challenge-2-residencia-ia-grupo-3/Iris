# Perfil Pedagógico Portátil: bloqueio de dados clínicos (História 3.1.3, #28)

Implementa RF-15 e RNF-03: o perfil guarda **apenas** barreiras funcionais observadas em sala e o histórico de
estratégias didáticas. CID, laudos, diagnósticos formais e medicação são rejeitados.

## Uso

```python
from iris.schemas.profile import validar_perfil, PerfilInvalidoError

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
| `codigo_anonimo` | 3 a 40 caracteres (letras, números, `_`, `-`); sem e-mail nem espaços |
| `barreiras_observadas[]` | `id_caracteristica` (do catálogo) + `observacao` opcional |
| `historico_estrategias[]` | `estrategia`, `resultado` (`eficaz`/`ineficaz`), `id_caracteristica` e `observacao` opcionais |
| `anotacoes_pedagogicas[]` | textos livres (até 1000 caracteres) |

Qualquer campo não declarado é rejeitado (`extra="forbid"`).

## O que é bloqueado

Chaves **e** valores são varridos recursivamente.

| Categoria | Exemplos |
|---|---|
| `cid` | `CID F90.0`, `F84`, `6A05`, "Classificação Internacional de Doenças" |
| `laudo` | laudo, atestado médico, relatório clínico, prontuário, receita médica, neuropsicológico |
| `diagnostico` | diagnóstico, TDAH, TEA, autismo, dislexia, transtorno, síndrome |
| `medicacao` | nomes de medicamentos, "medicação", "remédio", doses (`10 mg`), psiquiatra/neurologista |

Não são bloqueados: "avaliação diagnóstica", "diagnóstico pedagógico", códigos como `Q10`, "A4",
"ambiente estimulante", "receita de bolo".

## Privacidade

`str(exc)` **não** repete o trecho digitado (pode ir para logs). O trecho só sai em
`to_dict(incluir_trecho=True)`, para exibir ao docente na interface.

## Limites conhecidos

- Lista finita de termos e medicamentos; nomes novos exigem atualizar as constantes em `schemas/profile.py`.
- `F\d{2}` (ex.: `F10`) é tratado como CID; um código de exercício igual a esse seria um falso positivo.
- Deficiências sensoriais/físicas (ex.: "baixa visão") não são bloqueadas por serem informação de acessibilidade.
- Não detecta dados pessoais (nome do aluno, CPF) em texto livre; isso é responsabilidade do `security/pii_scrubber.py`.
- O schema do perfil é proposta a partir do RF-15; as histórias 3.1.1 e 3.1.2 podem refiná-lo.