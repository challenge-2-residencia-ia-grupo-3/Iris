"""
Script para injetar as Tarefas de Implementação Técnica (INVEST)
em cada História de Usuário de docs/backlog_rastreabilidade.md.
"""
from pathlib import Path

TASKS_MAP = {
    "1.1.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint FastAPI `POST /api/v1/materials/upload` com suporte a multipart/form-data e extração de texto bruto (`.txt`, `.pdf`, `.docx`).
- [ ] **[Backend]** Validação de tamanho (mínimo 50 caracteres e limite seguro de 2.000 palavras) com mensagens de erro estruturadas.
- [ ] **[Frontend]** Componente da Etapa 1 com área de colagem de texto (textarea acessível) e contador de caracteres/palavras em tempo real.
- [ ] **[Frontend]** Componente drag-and-drop de arquivos com feedback visual de formato aceito/rejeitado (WCAG 2.1 AA).
- [ ] **[Testes]** Testes unitários de extração de arquivos em `tests/api/test_materials.py` com mocks de PDF e DOCX.""",

    "1.1.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Módulo `src/iris/parsers/structural_decomposer.py` para isolar cabeçalho institucional, enunciados e alternativas.
- [ ] **[Backend]** Schema Pydantic `MaterialStructure` contendo blocos de contexto e lista de `QuestionItem`.
- [ ] **[RAG / IA]** Heurísticas e expressões regulares com fallback para modelo leve de NLP para identificar numeração de questões.
- [ ] **[Testes]** Testes com dataset sintético de 10 provas com layouts variados comprovando preservação sequencial.""",

    "1.1.3": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint `POST /api/v1/materials/ocr` para upload de imagens de provas (`.png`, `.jpg`).
- [ ] **[RAG / IA]** Integração com pipeline OCR / modelo de visão computacional (VLM) para transcrição fidedigna.
- [ ] **[RAG / IA]** Módulo de análise heurística de poluição visual (densidade de bordas e contraste da imagem).
- [ ] **[Frontend]** Exibição de preview da imagem digitalizada com indicador de densidade visual na tela do docente.
- [ ] **[Testes]** Testes de acurácia de OCR sobre amostra de provas escaneadas em diferentes resoluções.""",

    "1.2.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint `GET /api/v1/catalogs/characteristics` retornando o catálogo oficial de barreiras atômicas.
- [ ] **[Frontend]** Componente de seleção cirúrgica (Etapa 2) com filtros atômicos desacoplados de rótulo clínico.
- [ ] **[Frontend]** Bloqueio de avanço de fluxo com alerta acessível caso nenhuma característica seja selecionada.
- [ ] **[Testes]** Teste de renderização do catálogo e persistência do vetor de seleção no estado da sessão do cliente.""",

    "1.2.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Schema Pydantic para metadados de potencialidades, interesses e canais preferenciais (Princípio I DUA).
- [ ] **[Frontend]** Seletor de interesses temáticos (esportes, natureza, tecnologia) e campo de potencialidades na Etapa 2.
- [ ] **[RAG / IA]** Mapeamento dos metadados de potencialidade para injeção de contexto motivacional no prompt de adaptação.
- [ ] **[Testes]** Teste unitário verificando que a injeção de potencialidades não substitui os conceitos da trava curricular.""",

    "1.2.3": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint `POST /api/v1/audio/transcribe` para recepção de áudio docente (formato WAV/WebM até 60s).
- [ ] **[RAG / IA]** Pipeline de transcrição de áudio para texto (Speech-to-Text) com descarte imediato de PII.
- [ ] **[RAG / IA]** Mapeador semântico de fala para sugestão de checkboxes correspondentes do catálogo funcional.
- [ ] **[Frontend]** Componente de gravação de áudio no navegador com botão de confirmação das sugestões identificadas.
- [ ] **[Testes]** Testes de transcrição em amostra de áudios simulados de relatos docentes em português.""",

    "1.3.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Definição das diretrizes de andaime nos schemas de configuração de sessão (Nível 1, 2 e 3).
- [ ] **[Frontend]** Componente visual de calibração de suporte na Etapa 3 com cards explicativos de cada nível.
- [ ] **[Frontend]** Feedback visual detalhando as transformações estruturais de cada intensidade (Leve, Moderada, Intensiva).
- [ ] **[Testes]** Teste de validação garantindo que a diretiva de nível seja atribuída estritamente às características ativadas.""",

    "1.3.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Schema Pydantic para invariantes da Trava Curricular (conceitos obrigatórios, habilidades BNCC).
- [ ] **[Frontend]** Campo de texto estruturado na Etapa 3 com exemplos de travas e aviso de validação cognitiva.
- [ ] **[RAG / IA]** Validador preventivo de perda cognitiva (alerta anti-muleta) cruzando nível solicitado com trava definida.
- [ ] **[Testes]** Teste automatizado de detecção de incompatibilidade pedagógica (ex.: trava de inferência vs. andaime simplificador).""",

    "2.1.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Ingestão do corpus curado (DUA/CAST, MEC, Funções Executivas) no PostgreSQL com pgvector, com metadados por característica.
- [ ] **[RAG / IA]** Função de busca vetorial filtrada deterministicamente pelo `id_caracteristica` selecionado.
- [ ] **[RAG / IA]** Mapeador de contexto injetando trechos normativos e citações bibliográficas no prompt do Agente Estrategista.
- [ ] **[Testes]** Teste automatizado com RAGAS avaliando Context Precision e Faithfulness do trecho recuperado.""",

    "2.1.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Prompt e contrato Pydantic do Agente Extrator Curricular em `src/iris/agents/curriculum_extractor.py`.
- [ ] **[RAG / IA]** Extração determinística de vocabulário técnico, conceitos centrais e verbos de comando taxonômicos.
- [ ] **[Backend]** Estrutura de passagem de estado em memória com a lista de invariantes intocáveis.
- [ ] **[Testes]** Teste com 10 questões padrão aferindo a integridade dos conceitos extraídos pelo agente.""",

    "2.1.3": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Prompt e lógica de execução do Agente Adaptador em `src/iris/agents/adapter_agent.py`.
- [ ] **[RAG / IA]** Implementação da Regra de Isolamento de Escopo: restrição estrita das transformações à característica ativa.
- [ ] **[Backend]** Telemetria de latência e consumo de tokens por ciclo de geração multiagentes.
- [ ] **[Testes]** Teste de não-modificação de dimensões textuais não associadas à dificuldade selecionada.""",

    "2.1.4": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Prompt e motor de auditoria do Agente Auditor em `src/iris/agents/auditor_agent.py`.
- [ ] **[Backend]** Implementação do cálculo da Taxa de Retenção de Conceitos-Chave (TRCC) e validação de nível (SAEN).
- [ ] **[Backend]** Mecanismo de Circuit Breaker (`max_retries = 2`) para auto-correção sem loop infinito.
- [ ] **[Testes]** Teste de rejeição automática e disparo de refinamento quando TRCC < 95%.""",

    "2.2.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Componente da Etapa 5 com layout comparativo sincronizado lado a lado (Original vs. Adaptado).
- [ ] **[Frontend]** Cartões retráteis de justificativas pedagógicas com referências ao DUA e ao catálogo funcional.
- [ ] **[Frontend]** Indicadores visuais acessíveis destacando os andaimes cognitivos aplicados em cada questão.
- [ ] **[Testes]** Teste de responsividade e acessibilidade (WCAG 2.1 AA) em diferentes tamanhos de tela.""",

    "2.2.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Editor de texto inline em tempo real na coluna da atividade adaptada.
- [ ] **[Frontend]** Botão de aprovação formal por questão e confirmação final do docente (Human-in-the-Loop).
- [ ] **[Backend]** Endpoint `PUT /api/v1/sessions/{id}/review` persistindo em memória as edições manuais feitas pelo professor.
- [ ] **[Testes]** Teste garantindo que a exportação final permanece bloqueada até homologação explícita do docente.""",

    "2.2.3": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Compilador de PDF econômico em tons de cinza com tipografia sem serifa e cabeçalho neutro escolar.
- [ ] **[Backend]** Exportador para formato `.docx` com formatação limpa e editável via `python-docx`.
- [ ] **[Frontend]** Botões de download direto para PDF e DOCX com feedback visual de geração de arquivo.
- [ ] **[Testes]** Teste de validação estética do PDF gerado verificando ausência de rótulos clínicos ou estigmas no cabeçalho.""",

    "3.1.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Gerador de identificador aleatório anônimo (hash UUID desvinculado de nomes).
- [ ] **[Backend]** Schema Pydantic oficial para o Perfil Pedagógico Portátil em `src/iris/schemas/portable_profile.py`.
- [ ] **[Frontend]** Opção na interface para inicializar e nomear anonimamente uma ficha de perfil portátil.
- [ ] **[Testes]** Inspeção em código e testes automatizados comprovando ausência de persistência em banco de dados central.""",

    "3.1.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Componente de registro de feedback pedagógico com seletores de eficácia (`alta`, `média`, `baixa`).
- [ ] **[Frontend]** Campo de texto livre para anotação de observações pedagógicas contextuais sobre a intervenção.
- [ ] **[Backend]** Estruturação do registro no array `historico_intervencoes` do perfil portátil em memória.
- [ ] **[Testes]** Teste unitário de inclusão e histórico ordenado de estratégias no objeto de perfil.""",

    "3.1.3": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Validador estrito de schema Pydantic com `extra = "forbid"` rejeitando campos não declarados.
- [ ] **[Backend]** Filtro de termos clínicos restritos bloqueando padrões de CID médicos, remédios ou laudos médicos.
- [ ] **[Frontend]** Mensagem orientadora explicando que o perfil é estritamente pedagógico caso haja tentativa de inserção clínica.
- [ ] **[Testes]** Testes com dataset de dados clínicos sintéticos garantindo 100% de rejeição pelo validador.""",

    "3.2.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Serializador para download local do arquivo estruturado `.json` e do relatório de síntese `.pdf`.
- [ ] **[Frontend]** Ação de exportação com acionamento de download nativo do arquivo no dispositivo do professor.
- [ ] **[Backend]** Destruição da sessão em memória logo após a finalização do download pelo cliente.
- [ ] **[Testes]** Teste de validação do arquivo JSON baixado contra o schema oficial do Perfil Portátil.""",

    "3.2.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Componente de upload e parsing do arquivo `.json` do Perfil Pedagógico Portátil no início do fluxo.
- [ ] **[Frontend]** Pré-seleção automática das características funcionais e do nível de andaime recomendados no arquivo.
- [ ] **[Backend]** Validação de schema no upload com tratamento de arquivos corrompidos ou com formato inválido.
- [ ] **[Testes]** Teste ponta a ponta de restauração de parâmetros da sessão a partir de arquivo JSON válido.""",

    "4.1.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Módulo `src/iris/security/pii_scrubber.py` utilizando regex e modelo NER leve (ex.: spaCy pt-core-news-sm).
- [ ] **[Backend]** Substituição imediata e irreversível de nomes próprios e menções institucionais por marcadores genéricos.
- [ ] **[Testes]** Bateria de testes unitários com dataset de 50 cabeçalhos sintéticos de provas comprovando detecção >= 98%.
- [ ] **[Testes]** Teste de integridade comprovando que o payload enviado aos LLMs não possui dados identificáveis.""",

    "4.1.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Arquitetura stateless no FastAPI com ciclo de vida de dados restrito à sessão em memória.
- [ ] **[Backend]** Configuração da aplicação sem tabelas de cadastro de alunos em banco central.
- [ ] **[Testes]** Script de auditoria em CI/CD inspecionando o repositório para certificar ausência de modelos ORM de estudantes.""",

    "4.1.3": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Gerador de cabeçalho escolar neutro padrão em branco para inserção automática nos exports.
- [ ] **[Backend]** Descarte preventivo de marcadores acidentais no fechamento da sessão sem dicionário de memória.
- [ ] **[Frontend]** Pré-visualização do cabeçalho limpo com linhas pontilhadas na tela de exportação de material.
- [ ] **[Testes]** Teste comprovando que o documento gerado sai formatado para preenchimento manual em sala de aula.""",

    "4.1.4": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Configuração de formatadores de log (Loguru / Logging Python) filtrando payloads de requisições.
- [ ] **[Backend]** Registro exclusivo de metadados operacionais (status HTTP, latência em segundos, contagem de tokens, score TRCC).
- [ ] **[Testes]** Teste automatizado de inspeção de saída de logs assegurando ausência de textos de questões ou observações.""",

    "4.2.1": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Modelo Pydantic `CharacteristicCatalog` e `CharacteristicItem` com validação de campos obrigatórios.
- [ ] **[RAG / IA]** Criação do catálogo oficial `catalogs/tdah_caracteristicas_funcionais.json` estruturado por evidências.
- [ ] **[Testes]** Testes de carga e validação garantindo que novos catálogos (TEA, Dislexia) sejam carregados sem alterar código.""",

    "4.2.2": """### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Notebook e scripts da EDA 1 (corpus científico RAG: balanceamento por característica e tokens).
- [ ] **[RAG / IA]** Dataset de 30 a 50 questões escolares (Golden Benchmark) e scripts da EDA 2 (baseline Flesch PT-BR e comandos).
- [ ] **[RAG / IA]** Script do benchmark comparativo da Semana 3 comparando LLM Puro vs. Íris (RAG + Multiagentes).
- [ ] **[Testes]** Relatório automatizado de validação comprovando TRCC >= 95% e métricas RAGAS (Faithfulness >= 0.90).""",
}


def update_markdown():
    repo_root = Path(__file__).resolve().parent.parent
    md_file = repo_root / "docs" / "backlog_rastreabilidade.md"
    content = md_file.read_text(encoding="utf-8")

    # Divide onde começam as especificações
    spec_marker = "## 3. Especificação Completa das Issues (Temas, Épicos e Histórias)"
    if spec_marker not in content:
        print("Marcador de especificação não encontrado!")
        return

    top_part, spec_part = content.split(spec_marker, 1)

    import re
    # Encontra cada história do tipo ##### História X.Y.Z: Título
    pattern = re.compile(r"^(#####\s+História\s+(\d+\.\d+\.\d+):[^\n]+)", re.MULTILINE)
    
    matches = list(pattern.finditer(spec_part))
    new_spec_part = ""
    last_idx = 0

    for i, m in enumerate(matches):
        story_id = m.group(2)
        start_pos = m.start()
        next_pos = matches[i + 1].start() if i + 1 < len(matches) else len(spec_part)

        # Adiciona o texto entre a última história e a atual
        new_spec_part += spec_part[last_idx:start_pos]

        story_block = spec_part[start_pos:next_pos]

        # Se já tem o bloco de tarefas, remove para reinserir atualizado
        if "### Tarefas de Implementação Técnica" in story_block:
            story_block = re.split(r"\n+### Tarefas de Implementação Técnica", story_block, 1)[0]

        # Adiciona o bloco de tarefas mapeado
        tasks = TASKS_MAP.get(story_id, "")
        if tasks:
            story_block = story_block.rstrip() + f"\n\n{tasks}\n\n"

        new_spec_part += story_block
        last_idx = next_pos

    new_spec_part += spec_part[last_idx:]

    final_content = top_part + spec_marker + new_spec_part
    md_file.write_text(final_content, encoding="utf-8")
    print(f"Sucesso! {len(matches)} histórias atualizadas com Tarefas INVEST em {md_file}")


if __name__ == "__main__":
    update_markdown()

