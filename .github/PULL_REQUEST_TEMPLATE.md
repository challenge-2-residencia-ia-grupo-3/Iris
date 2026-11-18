## Issue Vinculada

<!--
Para vincular e fechar a issue automaticamente (movendo o card no GitHub Projects):
- Use sempre a palavra-chave em inglês: `Closes #123` (ou `Fixes #123` / `Resolves #123`).
- Para múltiplas issues, repita a palavra-chave: `Closes #12, Closes #34`.
- Se este PR NÃO fecha a issue (entrega parcial), substitua por `Refs #123`.
-->

Closes #<numero>

## Resumo

<!-- Descreva objetivamente o que foi alterado e o motivo da mudança. -->

## Tipo de Mudança

- [ ] `feat`: Nova funcionalidade
- [ ] `fix`: Correção de bug
- [ ] `refactor`: Refatoração sem alteração de comportamento
- [ ] `docs`: Documentação / catálogo
- [ ] `test`: Adição ou ajuste de testes
- [ ] `chore` / `ci`: Configuração, dependências ou workflows

## Como Testar e Evidências

<!-- Informe os comandos executados e os resultados observados (ex.: `make test`, `make check`). -->

- Comando: `make test`
- Resultado:

## Checklist

- [ ] A branch de destino deste PR é `dev` (ou `dev` -> `main`, conforme `.github/workflows/enforce-pr-source.yml`)
- [ ] Os testes automatizados (`make test`) estão passando localmente
- [ ] **Pilar 1 (Barreiras Funcionais):** não introduz rótulos clínicos, diagnósticos ou laudos
- [ ] **Pilar 2 (Trava Curricular):** preserva integralmente enunciados, alternativas e objetivos pedagógicos (quando aplicável)
- [ ] **Pilar 3 (Privacy by Design / LGPD):** não persiste dados de alunos nem expõe PII/conteúdo sensível em logs, erros ou caches
- [ ] Documentação atualizada (se aplicável)

