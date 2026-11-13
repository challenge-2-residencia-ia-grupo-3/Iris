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
| `codigo_anonimo` | `aluno-` + 8 a 32 hex minúsculos |
| `criado_em` | data/hora com fuso (UTC por padrão) |
| `caracteristicas_selecionadas[]` | ids do catálogo, sem repetição |
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
| `diagnostico` | "diagnóstico médico/clínico", "tem diagnóstico", TDAH, TEA/TOC (siglas em maiúsculas), autismo, "no espectro", dislexia, "transtorno de/do…", síndrome |
| `medicacao` | nomes de medicamentos, "medicação", "remédio", doses (`10 mg`), psiquiatra/neurologista |

Não são bloqueados: "avaliação diagnóstica", "diagnóstico pedagógico", "diagnóstico inicial da turma",
"a troca de sala causou transtorno", "ele concerta os erros", "garrafa de 500 ml", "toc toc", códigos como
`Q10`, "A4", "ambiente estimulante", "receita de bolo". Como *nome de campo*, `diagnostico`/`transtorno` são sempre bloqueados.

## Privacidade

`str(exc)` **não** repete o trecho digitado (pode ir para logs). O trecho só sai em
`to_dict(incluir_trecho=True)`, para exibir ao docente na interface.

## Limites conhecidos

- Lista finita de termos e medicamentos; nomes novos exigem atualizar as constantes em `schemas/profile.py`.
- `F\d{2}` (ex.: `F10`) é tratado como CID; um código de exercício igual a esse seria um falso positivo.
- Deficiências sensoriais/físicas (ex.: "baixa visão") não são bloqueadas por serem informação de acessibilidade.
- Não detecta dados pessoais (nome do aluno, CPF) em texto livre; isso é responsabilidade do `security/pii_scrubber.py`.
- Termos clínicos dentro de identificadores com sublinhado (`tdah_formal`) também são detectados.
- O histórico de eficácia (`historico_estrategias`) é proposta da 3.1.2 (#27) e pode ser refinado lá.
- Não há rota de API nem botão no frontend: a criação e o download ainda precisam ser ligados.
