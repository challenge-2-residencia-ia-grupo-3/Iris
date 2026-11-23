#!/usr/bin/env python3
"""Gera o PDF de entrega da Semana 4 (Sistema Multiagentes — Plataforma Íris).

Uso:
    cd iris
    .venv/bin/python3 scripts/gerar_pdf_multiagentes.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = REPO_ROOT / "docs" / "figuras"
OUT_DIR = REPO_ROOT / "docs" / "entregas"
OUT_PDF = OUT_DIR / "semana4_sistema_multiagentes.pdf"

CSS = """
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.4;
    color: #132325;
}
.hero {
    background-color: #143d40;
    color: #ffffff;
    padding: 13pt 16pt;
    margin-bottom: 10pt;
}
.hero-kicker {
    font-size: 8pt;
    color: #9ec5c7;
    font-weight: bold;
    margin-bottom: 3pt;
}
.hero-title {
    font-size: 16pt;
    font-weight: bold;
    color: #ffffff;
    margin: 0 0 4pt 0;
}
.hero-sub {
    font-size: 9.2pt;
    color: #edf2f2;
    margin: 0;
}
.meta-box {
    background-color: #eef3f3;
    border: 0.7pt solid #cbd5e1;
    padding: 7pt 10pt;
    margin-bottom: 10pt;
    font-size: 8.6pt;
    line-height: 1.38;
}
h1 {
    font-size: 12.2pt;
    font-weight: bold;
    color: #143d40;
    border-left: 3.5pt solid #143d40;
    padding-left: 7pt;
    margin: 4pt 0 7pt 0;
}
h2 {
    font-size: 10.4pt;
    font-weight: bold;
    color: #132325;
    margin: 10pt 0 4pt 0;
}
p {
    margin: 0 0 6pt 0;
    text-align: left;
}
ul, ol {
    margin: 0 0 7pt 0;
    padding-left: 15pt;
}
li {
    margin-bottom: 3.5pt;
}
code {
    font-family: Courier, monospace;
    font-size: 8.1pt;
    background-color: #eef3f3;
    color: #132325;
}
pre {
    font-family: Courier, monospace;
    font-size: 7.45pt;
    line-height: 1.32;
    background-color: #f8fafc;
    border: 0.7pt solid #cbd5e1;
    padding: 6.5pt 8.5pt;
    margin: 5pt 0 9pt 0;
    white-space: pre-wrap;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 6pt 0 10pt 0;
    font-size: 8pt;
    line-height: 1.3;
}
td {
    padding: 5pt 5.5pt;
    vertical-align: top;
    border: 0.6pt solid #cbd5e1;
}
tr.tbl-head td {
    background-color: #143d40;
    color: #ffffff;
    font-weight: bold;
    border-color: #143d40;
}
table code {
    font-size: 7.2pt;
}
.callout {
    background-color: #f7fafa;
    border-left: 3pt solid #156f4e;
    padding: 6.5pt 9.5pt;
    margin: 7pt 0 9pt 0;
    font-size: 8.8pt;
}
.callout-info {
    background-color: #eef3f3;
    border-left: 3pt solid #335c67;
    padding: 6.5pt 9.5pt;
    margin: 7pt 0 9pt 0;
    font-size: 8.8pt;
}
.figure {
    margin: 6pt 0 8pt 0;
    text-align: center;
}
.caption {
    font-size: 8pt;
    color: #4b6163;
    margin-top: 3pt;
    text-align: center;
}
"""


def _wrap_page(body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8" /></head>
<body>{body_html}</body>
</html>"""


def _build_pages() -> list[str]:
    page1 = _wrap_page("""
  <div class="hero">
    <div class="hero-kicker">RESIDÊNCIA EM INTELIGÊNCIA ARTIFICIAL APLICADA • UnB / Lab Livre / Eldorado / Softex / MCTI</div>
    <div class="hero-title">Íris — Primeiro Protótipo Multiagente (Semana 4)</div>
    <p class="hero-sub">Arquitetura, responsabilidades, fluxo de colaboração e demonstração ponta a ponta do sistema multiagentes para adaptação pedagógica inclusiva (TDAH)</p>
  </div>

  <div class="meta-box">
    <b>Challenge 2:</b> Qualidade de Vida &nbsp;|&nbsp;
    <b>Equipe:</b> Grupo 3 (Turma 1) &nbsp;|&nbsp;
    <b>Canal Teams:</b> <code>4_Second Challenge</code><br/>
    <b>Repositório GitHub:</b> https://github.com/challenge-2-residencia-ia-grupo-3/Iris &nbsp;|&nbsp;
    <b>Módulos:</b> <code>iris/backend/src/iris/agents/</code>
  </div>

  <h1>1. Visão Geral e Arquitetura dos Agentes</h1>
  <p>
    A plataforma <b>Íris</b> apoia professores na adaptação de avaliações e atividades pedagógicas para alunos com TDAH,
    atuando de forma cirúrgica sobre barreiras funcionais observáveis sem simplificar ou resolver o currículo
    (<i>anti-efeito muleta</i>). O sistema substitui o prompt monolítico por uma cadeia <b>100% stateless e em memória</b>
    coordenada por <code>MultiAgentOrchestrator</code> (<code>agents/orchestrator.py</code>), executada após sanitização
    preventiva de dados pessoais (<code>sanitize_pii</code> — Zero-Retention) e decomposição estrutural determinística
    (<code>decompose_material</code>).
  </p>

  <div class="figure">
    <img src="multiagentes_arquitetura.svg" style="width: 91%;" />
    <div class="caption">Figura 1 — Arquitetura do Sistema Multiagentes da plataforma Íris, integrando Gateway PII, Decompositor Estrutural, Base RAG e os 4 agentes especializados.</div>
  </div>

  <div class="callout">
    <b>Conformidade com Privacy by Design (LGPD):</b> nenhum texto bruto com identificadores pessoais entra na fila dos
    agentes ou em logs operacionais. Além da orquestração principal em <code>MultiAgentOrchestrator</code>, o fluxo foi
    prototipado como grafo de estados em <b>LangGraph</b> (<code>eval/arquitetura_langgraph.py</code>),
    permitindo pausa explícita para revisão docente (<code>interrupt()</code>) sem persistir dados sensíveis em banco.
  </div>
""")

    page2 = _wrap_page("""
  <h1>2. Descrição das Responsabilidades de Cada Agente</h1>
  <p>
    O entregável solicita a implementação de no mínimo 2 agentes especializados. A plataforma Íris implementa
    <b>4 agentes especializados</b> que cobrem integralmente os papéis de análise, pesquisa científica, adaptação de
    comunicação e validação com auto-correção:
  </p>

  <table>
    <tr class="tbl-head">
      <td style="width: 19%;">Agente no Íris<br/>(Módulo / Issue)</td>
      <td style="width: 17%;">Papel Multiagentes</td>
      <td style="width: 21%;">Entradas e Contratos</td>
      <td style="width: 20%;">Saídas (Pydantic)</td>
      <td style="width: 23%;">Guardrails Determinísticos e Fallback</td>
    </tr>
    <tr>
      <td><b>1. Extrator Curricular</b><br/><code>curriculum_</code><br/><code>extractor.py</code> (#17)</td>
      <td><b>Analysis Agent</b><br/>(Análise e síntese de invariantes curriculares)</td>
      <td>Enunciado da questão, contexto, disciplina, ano escolar e travas manuais do docente.</td>
      <td><code>ExtractionResult</code> (conceitos obrigatórios, termos intocáveis, verbo BNCC e alerta anti-muleta).</td>
      <td>Normaliza verbo BNCC para infinitivo, injeta travas manuais e possui fallback léxico/regex offline.</td>
    </tr>
    <tr>
      <td><b>2. Estrategista RAG</b><br/><code>strategist_</code><br/><code>agent.py</code> (#16)</td>
      <td><b>Research Agent</b><br/>(Recuperação de evidências DUA/MEC)</td>
      <td><code>StrategyRequest</code> (características selecionadas, nível 1–3, invariantes e enunciado).</td>
      <td><code>StrategyResult</code> (<code>diretiva</code>, <code>intervencoes</code>, <code>fontes</code> citadas e telemetria).</td>
      <td>Filtro pré-prompt restrito à barreira; veta itens sem <code>[Tn]</code>, &gt; 40 palavras, de traço não selecionado ou cópia (&ge; 12 palavras). Fallback do catálogo.</td>
    </tr>
    <tr>
      <td><b>3. Adaptador Pedagógico</b><br/><code>adapter_agent.py</code> (#18)</td>
      <td><b>Communication Agent</b><br/>(Adaptação da apresentação ao perfil)</td>
      <td><code>AdaptationRequest</code> (enunciado, característica, nível, invariantes, diretiva e feedback).</td>
      <td><code>AdaptationResult</code> (<code>texto_adaptado</code>, justificativas DUA e <code>ScopeReport</code>).</td>
      <td>Validação via <code>verificar_escopo()</code> (palavras, ordem LCS e trava). Em caso de falha, aciona saída de reserva determinística por nível.</td>
    </tr>
    <tr>
      <td><b>4. Auditor de Integridade</b><br/><code>auditor.py</code> (#19)</td>
      <td><b>Validation Agent</b><br/>(Auditoria, inconsistências e auto-correção)</td>
      <td>Enunciado original, minuta adaptada, <code>CurriculumInvariants</code> e traços não marcados.</td>
      <td><code>ResultadoAuditoria</code> e <code>RelatorioCiclo</code> (<code>aprovado</code>, <code>texto_final</code>, revisão humana).</td>
      <td>TRCC determinística &ge; 95%, 100% dos termos intocáveis, detecção de gabarito/cálculo resolvido e juiz LLM restrito a <code>trechos_novos</code>.</td>
    </tr>
  </table>

  <h2>Contratos de Integração e Separação de Papéis</h2>
  <div class="callout-info">
    <ul>
      <li><b>Fonte Única de Verdade (Catálogo TDAH):</b> <code>rag/catalogs/tdah_caracteristicas_funcionais.json</code> define as características funcionais e mapeia cada <code>id_caracteristica</code> para uma única barreira no RAG, garantindo atuação cirúrgica sem interferir em traços não assinalados pelo docente.</li>
      <li><b>Camada de Degradação Segura:</b> cada agente conta com fallback determinístico explícito (<code>motivo_fallback</code>) e telemetria de latência/tokens sem PII (<code>ZeroPiiLogFilter</code>), respeitando os orçamentos RNF-07 (&le; 40 s nos níveis 2 e 3) e RNF-08.</li>
      <li><b>Orquestração Dual (Pipeline + LangGraph):</b> além do <code>MultiAgentOrchestrator</code> utilizado pela API FastAPI e pelo frontend Next.js, o grafo completo em <code>eval/arquitetura_langgraph.py</code> modela nós, arestas condicionais e pausa <code>interrupt()</code> para revisão docente.</li>
    </ul>
  </div>
""")

    page3 = _wrap_page("""
  <h1>3. Fluxo de Interação e Colaboração entre os Agentes</h1>
  <p>
    A colaboração ocorre por passagem explícita de contratos tipados (Pydantic) entre os quatro agentes, com destaque
    para o <b>ciclo fechado de feedback e auto-correção</b> entre o <b>Agente Auditor (#19)</b> e o
    <b>Agente Adaptador (#18)</b> via <code>CicloComAuditor</code>:
  </p>

  <div class="figure">
    <img src="multiagentes_sequencia.svg" style="width: 96%;" />
    <div class="caption">Figura 2 — Diagrama de sequência mostrando os contratos trocados por questão e o laço de auto-correção limitado pelo Circuit Breaker.</div>
  </div>

  <ul>
    <li><b>1. Análise Curricular (<code>Extrator</code>):</b> recebe o enunciado sanitizado e fixa os conceitos da trava curricular, termos técnicos intocáveis, verbo de comando BNCC e o alerta anti-muleta que todos os demais agentes devem respeitar.</li>
    <li><b>2. Recuperação Fundamentada (<code>Estrategista RAG</code>):</b> consulta a base científica DUA/MEC filtrada estritamente pela barreira selecionada e gera diretivas curtas com citações verificadas <code>[T1..Tn]</code>.</li>
    <li><b>3. Adaptação Cirúrgica (<code>Adaptador</code>):</b> reescreve apenas a apresentação da questão segundo o nível de andaime (1, 2 ou 3) e valida a aderência pelo laudo determinístico <code>verificar_escopo()</code>.</li>
    <li><b>4. Auditoria e Auto-Correção (<code>Auditor &harr; Adaptador</code>):</b> se a minuta perder conceito obrigatório (TRCC &lt; 95%), suprimir termo intocável ou antecipar a resposta, o <b>Auditor</b> reprova e devolve um <code>feedback()</code> objetivo junto com a minuta reprovada para que o <b>Adaptador</b> corrija na tentativa seguinte.</li>
    <li><b>5. Circuit Breaker e Human-in-the-Loop:</b> o laço executa no máximo <b>3 tentativas</b> (1 inicial + até 2 retentativas, equivalente a <code>max_retries = 2</code> no ADR-06). Se nenhuma atingir conformidade, o sistema falha fechado com <code>requer_revisao_humana=True</code> e encaminha a questão à Etapa 5 para decisão do docente.</li>
  </ul>
""")

    page4 = _wrap_page("""
  <h1>4. Demonstração Executada Ponta a Ponta e Validação</h1>
  <p>
    Registro da execução real completa de <code>scripts/demo_multiagentes.py --demo</code> com o modelo
    <b>Anthropic Claude Haiku</b> (<code>anthropic / claude-haiku-5-5</code>) e a base RAG local (<code>bm25</code>),
    cobrindo dois cenários complementares do contexto educacional:
  </p>

  <h2>4.1. Cenário 1 — Fluxo Completo com Aprovação Direta (Q13, Matemática, Nível 2)</h2>
  <p>
    <b>Questão original:</b> <i>"Resolva a equação 2x + 6 = 14 e verifique se o valor encontrado está correto."</i><br/>
    <b>Barreira selecionada:</b> <code>sobrecarga_memoria_trabalho_comandos_multiplos</code> &nbsp;|&nbsp;
    <b>Latência total:</b> 12,8 s (limite RNF-07: 40 s) &nbsp;|&nbsp; <b>Tokens:</b> 7.837
  </p>
  <pre>[1] Agente Extrator Curricular (#17 — Analysis Agent) | 1855.1 ms (fallback=False)
    Verbo BNCC       : resolver
    Operação         : isolar a incógnita aplicando operações inversas e verificar a solução substituindo-a na equação
    Conceitos Trava  : ['equação', '2x + 6 = 14', 'valor encontrado', 'verifique']
    Termos Intocáveis: ['2x + 6 = 14', 'equação']
    Alerta AntiMuleta: Proibido informar o valor de x ou mostrar as etapas de isolamento (como 14 - 6 = 8 e 8 ÷ 2 = 4).

[2] Agente Estrategista RAG (#16 — Research Agent) | método=bm25 | fontes=5 | fora_filtro=0
    Diretiva         : Para sobrecarga_memoria_trabalho_comandos_multiplos: Converta os comandos encadeados em uma lista numerada com caixas de seleção, deixando cada ação em um item próprio e iniciando cada etapa por um verbo de comando, para que o aluno possa conferir o que já cumpriu. [T1]
    Fonte [T1]       : Um conjunto de diretrizes para a adaptação de avaliações de aprendizagem para alunos com TDAH, p. 11-12. Disponível em: https://periodicos.utfpr.edu.br/rtr/article/download/17713/10262

[3 &amp; 4] Loop Agente Adaptador (#18) &lt;-&gt; Agente Auditor (#19)
  -&gt; Tentativa 1: APROVADA | TRCC=100% | Escopo=OK | ResoluçãoIndevida=False

[Saída Final Entregue]
  1. [ ] **Resolva** a equação 2x + 6 = 14
  2. [ ] **Verifique** se o valor encontrado está correto.
Justificativas DUA : ['2 comandos separados em lista de verificação numerada, na ordem original.', 'Verbo de comando destacado em negrito no início de cada etapa.']
Status Auditoria   : aprovado=True | requer_revisao_humana=False | ciclo=10929.0 ms (limite RNF-07=40000 ms)</pre>

  <div class="callout">
    <b>Leitura pedagógica do Cenário 1:</b> os dois verbos de comando da questão original foram separados em uma lista
    numerada com caixas de verificação, sem simplificar a equação <code>2x + 6 = 14</code> e sem fornecer pistas sobre
    o valor de <code>x</code>. O Auditor confirmou <b>TRCC = 100%</b> e aprovou na <b>Tentativa 1</b>.
  </div>
""")

    page5 = _wrap_page("""
  <h2>4.2. Cenário 2 — Colaboração e Auto-Correção Auditor &harr; Adaptador (Q18, Ciências, Nível 3)</h2>
  <p>
    <b>Questão original:</b> <i>"Leia o texto e responda: por que as plantas precisam de luz? As plantas produzem o próprio alimento por meio da fotossíntese, processo que usa a luz do sol."</i><br/>
    <b>Objetivo:</b> evidenciar o Auditor detectando omissão curricular na Tentativa 1 e guiando a correção do Adaptador na Tentativa 2 &nbsp;|&nbsp; <b>Latência total:</b> 18,6 s &nbsp;|&nbsp; <b>Tokens:</b> 8.382
  </p>
  <pre>[1] Agente Extrator Curricular (#17 — Analysis Agent) | 1414.5 ms (fallback=False)
    Verbo BNCC       : responder
    Conceitos Trava  : ['plantas', 'fotossíntese', 'luz', 'alimento', 'luz do sol']
    Termos Intocáveis: ['fotossíntese', 'luz do sol']

[2] Agente Estrategista RAG (#16 — Research Agent) | método=bm25 | fontes=5 | fora_filtro=0
    Diretiva [T3][T2]: Separe a questão em passos numerados, cada um com seu próprio espaço de resposta logo abaixo, para que o aluno trate uma operação por vez sem precisar memorizar os demais.
    Diretiva [T1]    : Mantenha o comando principal logo no início, com texto de apoio curto, e destaque as palavras-chave.
    Diretiva [T3]    : Inclua ao final da questão um lembrete para o aluno conferir se preencheu todos os passos.

[3 &amp; 4] Loop Agente Adaptador (#18) &lt;-&gt; Agente Auditor (#19)
  -&gt; Tentativa 1: REPROVADA | TRCC=80% | Escopo=VIOLADO | ResoluçãoIndevida=False
     Minuta reprovada : **Passo 1** / [ ] **Leia** o texto / **Passo 2** / **Responda**: por que as [termo omitido] precisam de luz? ...
     Motivo Auditor   : TRCC 80% abaixo de 95%; ausentes: ['plantas']; juiz: intrusão em bloqueio_iniciacao_tarefas_abertas. [ ] **Leia** o texto
     Feedback -&gt; Adapt: Reinclua os conceitos-chave ausentes, exatamente como no original: plantas.
  -&gt; Tentativa 2: APROVADA | TRCC=100% | Escopo=OK | ResoluçãoIndevida=False

[Saída Final Entregue]
  **Passo 1**
  [ ] **Leia** o texto

  **Passo 2**
  **Responda**: por que as plantas precisam de luz?
  Resposta: ______________________________

  As plantas produzem o próprio alimento por meio da fotossíntese, processo que usa a luz do sol.
  Revise se você preencheu todos os passos.
Status Auditoria   : aprovado=True | requer_revisao_humana=False | ciclo=6687.4 ms (limite RNF-07=40000 ms)</pre>

  <h2>4.3. Evidências de Testes Automatizados e Como Reproduzir</h2>
  <div class="callout">
    <ul>
      <li><b>Suíte automatizada dos agentes</b> (<code>pytest</code> em <code>test_multiagent_orchestrator.py</code>, <code>test_curriculum_extractor.py</code>, <code>test_strategist_agent.py</code>, <code>test_adapter_agent.py</code> e <code>test_auditor.py</code>): <b>116 testes aprovados</b> (153 subtestes aprovados em 1,87 s).</li>
      <li><b>Execução via terminal:</b> dentro de <code>iris/</code>, execute <code>make multiagentes</code> (ou offline com <code>PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 scripts/demo_multiagentes.py --demo --provider extractive</code>).</li>
      <li><b>Execução via aplicação web:</b> execute <code>make up</code> em <code>iris/</code> e acesse <code>http://localhost:3000</code> (etapas <code>/etapa-1</code> &rarr; <code>/etapa-5</code>, com os 4 cards dos agentes em <code>/etapa-4</code>) ou o grafo LangGraph em <code>http://127.0.0.1:8000</code>.</li>
    </ul>
  </div>
""")
    return [page1, page2, page3, page4, page5]


def _stamp_headers_and_footers(pdf_path: Path) -> int:
    doc = pymupdf.open(pdf_path)
    total = len(doc)
    for idx, page in enumerate(doc, start=1):
        w = page.rect.width
        h = page.rect.height
        if idx > 1:
            page.insert_text(
                pymupdf.Point(42, 26),
                "Íris — Challenge 2 (Grupo 3) • Primeiro Protótipo Multiagente (Semana 4)",
                fontsize=7.8,
                fontname="helv",
                color=(0.30, 0.38, 0.39),
            )
            page.draw_line(pymupdf.Point(42, 31), pymupdf.Point(w - 42, 31), color=(0.82, 0.86, 0.87), width=0.6)
        page.draw_line(pymupdf.Point(42, h - 34), pymupdf.Point(w - 42, h - 34), color=(0.82, 0.86, 0.87), width=0.6)
        page.insert_text(
            pymupdf.Point(42, h - 22),
            "RES IA ELD UNB — Canal 4_Second Challenge",
            fontsize=7.8,
            fontname="helv",
            color=(0.30, 0.38, 0.39),
        )
        pg_label = f"Página {idx} de {total}"
        page.insert_text(
            pymupdf.Point(w - 42 - len(pg_label) * 4.2, h - 22),
            pg_label,
            fontsize=7.8,
            fontname="helv",
            color=(0.30, 0.38, 0.39),
        )
    temp_path = pdf_path.with_suffix(".stamped.pdf")
    doc.save(temp_path, garbage=4, deflate=True)
    doc.close()
    temp_path.replace(pdf_path)
    return total


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = _build_pages()
    mediabox = pymupdf.paper_rect("a4")
    where = pymupdf.Rect(42, 40, mediabox.width - 42, mediabox.height - 44)

    merged = pymupdf.open()
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, html in enumerate(pages, start=1):
            page_pdf = Path(tmpdir) / f"p{idx}.pdf"
            archive = pymupdf.Archive(str(FIG_DIR))
            story = pymupdf.Story(html=html, user_css=CSS, archive=archive)
            writer = pymupdf.DocumentWriter(str(page_pdf))
            dev = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(dev, None)
            writer.end_page()
            writer.close()
            if more:
                raise RuntimeError(f"Conteúdo da página {idx} excedeu a área útil A4.")
            with pymupdf.open(page_pdf) as pdoc:
                merged.insert_pdf(pdoc)
    merged.save(OUT_PDF, garbage=4, deflate=True)
    merged.close()

    total_pages = _stamp_headers_and_footers(OUT_PDF)
    print(f"PDF gerado com sucesso: {OUT_PDF} ({total_pages} páginas, {OUT_PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
