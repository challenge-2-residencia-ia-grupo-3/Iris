"""etapas_explicadas.py: o que cada etapa e cada agente do Íris faz, com exemplo real e rastro das chamadas.

Pergunta que responde: "o que esta peça faz, por que existe, o que entrou e saiu dela de verdade, e
o que o modelo de IA recebeu e devolveu em cada chamada?" (rastro no estilo Langfuse).

Lê (só leitura, só biblioteca padrão; não importa nada do código do grupo):
    pacote/outputs/26-rastro-pipeline-resumo.json   runs mais recentes de cada material
    pacote/reports/pipeline/<run_id>.jsonl          rastro completo de cada run (uma linha por etapa)
    pacote/reports/pipeline/adv-*.jsonl             só para etapas que aparecem apenas nos casos adversariais
    pacote/outputs/27-mapa-codigo.json              etapas macro (1..10) com status e evidência
    <grupo>/backend/src/iris/agents/*.py            prompts de sistema, lidos como texto (ast)
    <grupo>/rag/iris-rag/pacote/gerar.py            instruções do Estrategista, lidas como texto
Escreve:
    pacote/outputs/31-etapas.json

Os textos dos documentos do RAG podem ter licença restrita e o 31-etapas.json vai para o git: os trechos
são trocados por '[trecho Tn: <chunk_id>, N caracteres]' e, no fim, um teste procura no JSON qualquer
sequência de 200+ caracteres que exista no pacote/chunks.jsonl. Se achar, o script falha (exit 1).

Uso:  cd pacote && make etapas      (ou python ../bancada/pipeline/etapas_explicadas.py --grupo <clone>)
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "pacote"
OUTPUTS = PACOTE / "outputs"
REPORTS = PACOTE / "reports" / "pipeline"
CHUNKS = PACOTE / "chunks.jsonl"
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("onde", Path(__file__).resolve().parents[1] / "onde.py")
_onde = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_onde)
GRUPO_PADRAO = str(_onde.grupo())

LIM_EXEMPLO = 600
LIM_PROMPT = 4000
LIM_SAIDA = 3000
JANELA = 200  # tamanho mínimo de cópia literal de trecho do RAG que reprova o arquivo

# ------------------------------------------------------------------ explicações (escritas à mão)
# Conferidas nas docstrings e no corpo das funções do grupo (commit 65e1f09). "a confirmar" = não verificado.
EXPLICACOES: dict[str, dict[str, Any]] = {
    "upload_tamanho": {
        "nome": "Tamanho do arquivo",
        "macro": 1, "agente": False, "dados_pessoais": True,
        "o_que_faz": "Confere se o arquivo enviado pelo professor tem até 10 MB antes de abri-lo.",
        "por_que_existe": "O arquivo é lido inteiro na memória do servidor; um arquivo enorme poderia travar o sistema para todos.",
        "se_falhar": "O envio é recusado com a mensagem de que o arquivo passa do limite de 10 MB (código FILE_TOO_LARGE).",
    },
    "entrada_texto": {
        "nome": "Texto colado",
        "macro": 1, "agente": False, "dados_pessoais": True,
        "o_que_faz": "Quando o professor cola o texto em vez de enviar arquivo, confere se o texto não está vazio ou só com espaços.",
        "por_que_existe": "Evita mandar um pedido vazio para as etapas seguintes.",
        "se_falhar": "Aparece a mensagem de texto vazio (código EMPTY_TEXT) e nada é processado.",
    },
    "extracao_documento": {
        "nome": "Leitura do arquivo",
        "macro": 3, "agente": False, "dados_pessoais": True,
        "o_que_faz": "Abre o arquivo (.pdf, .docx ou .txt) e tira dele só o texto, como quem copia e cola o conteúdo; em .docx também lê as tabelas. Não lê imagem: não há OCR para prova escaneada (issue #6 aberta).",
        "por_que_existe": "Todas as etapas seguintes trabalham com texto; o professor não precisa redigitar a atividade.",
        "se_falhar": "Formato não aceito (UNSUPPORTED_FORMAT) ou arquivo ilegível; numa prova escaneada sai pouco ou nenhum texto e a validação reclama de texto curto.",
    },
    "filtro_pii": {
        "nome": "Filtro de dados pessoais",
        "macro": 2, "agente": False, "dados_pessoais": True,
        "o_que_faz": "Procura dados que identificam pessoas (CPF, e-mail, matrícula, telefone, nome depois de 'Aluno:' ou 'Professor:', nome de escola) e troca por etiquetas como [ESTUDANTE] e [CPF]. Funciona por padrões de texto (regex), sem IA, e não guarda o original.",
        "por_que_existe": "Impede que nome e documentos do aluno cheguem ao modelo de IA e aos registros (LGPD, RNF-01/02).",
        "se_falhar": "O nome ou documento do aluno segue para o modelo e pode aparecer no texto adaptado; nomes soltos no meio do texto, sem rótulo como 'Aluno:', passam (no M3, o nome plantado passou).",
    },
    "validacao_conteudo": {
        "nome": "Tamanho do texto",
        "macro": 1, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Conta caracteres e palavras do texto já filtrado e recusa se tiver menos de 50 caracteres ou mais de 100.000.",
        "por_que_existe": "Texto curto demais não dá para analisar; texto longo demais não cabe de uma vez na memória de trabalho do modelo (a janela de contexto).",
        "se_falhar": "Mensagem de texto curto (TEXT_TOO_SHORT) ou longo demais (CONTEXT_WINDOW_EXCEEDED), pedindo para dividir o material.",
    },
    "decomposicao_estrutural": {
        "nome": "Separação em questões",
        "macro": 4, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Separa a atividade em cabeçalho, textos de apoio, questões (com alternativas) e blocos não reconhecidos, olhando a numeração ('1)', 'Questão 1:'). Usa regras, sem IA.",
        "por_que_existe": "Cada questão é adaptada separadamente, e o texto de apoio precisa ficar ligado às questões que dependem dele.",
        "se_falhar": "Questões grudadas numa só, alternativas perdidas ou um subtítulo tomado por questão (no M3, '1. Contexto' e '2. O processo' viraram questões: 3 detectadas para 1 real).",
    },
    "organizacao_texto_corrido": {
        "nome": "Organização do texto corrido",
        "macro": 4, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Monta uma árvore do texto: títulos, seções, parágrafos e listas, na ordem original e sem apagar nada. É chamada por dentro da separação em questões.",
        "por_que_existe": "Materiais que são texto (apostila, capítulo) e não lista de questões também precisam de estrutura para serem adaptados (história 1.1.4, issue #53).",
        "se_falhar": "A estrutura mostrada ao professor fica errada; hoje nenhum agente usa essa árvore, então a adaptação não muda.",
    },
    "selecao_caracteristicas": {
        "nome": "Dificuldades escolhidas",
        "macro": 6, "agente": False, "dados_pessoais": True,
        "o_que_faz": "Registra quais dificuldades do aluno o professor marcou no catálogo de TDAH (aqui 1 de 10) e bloqueia as demais. Recusa campos clínicos ou extras, como CID ou laudo.",
        "por_que_existe": "A adaptação mexe só na dificuldade escolhida, sem tirar autonomia do aluno no resto, e o sistema nunca recebe diagnóstico médico.",
        "se_falhar": "A seleção é recusada (por exemplo com campo clínico ou nenhuma característica) e nada é adaptado.",
    },
    "perfil_pedagogico": {
        "nome": "Perfil do aluno",
        "macro": 6, "agente": False, "dados_pessoais": True,
        "o_que_faz": "Confere o formato do perfil: código anônimo, barreiras observadas, estratégias já usadas e anotações (cada uma com até 1000 caracteres). Nenhuma rota da API chama esta função ainda.",
        "por_que_existe": "O perfil acompanha o aluno sem nome; um formato fechado impede que se guarde dado que não devia.",
        "se_falhar": "O perfil é recusado ao importar (PerfilInvalidoError) com a lista do que está fora do formato.",
    },
    "extrator_curricular": {
        "nome": "Agente Extrator Curricular",
        "macro": 5, "agente": True, "dados_pessoais": False,
        "o_que_faz": "Agente de IA que lê a questão e lista o que não pode mudar na adaptação: conceitos e termos técnicos, o verbo de comando (explicar, calcular...) e um alerta para não entregar a resposta. Se a IA falhar ou o provedor não tiver modelo, usa regras de texto como reserva.",
        "por_que_existe": "Evita que a adaptação 'facilite' tirando o conteúdo que a questão avalia (empobrecimento curricular).",
        "se_falhar": "Com conceitos errados, o laudo de escopo passa a proteger as palavras erradas e pode deixar sumir um conceito avaliado sem aviso.",
    },
    "busca_rag": {
        "nome": "Busca de estratégias (RAG)",
        "macro": 7, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Procura na base de documentos pedagógicos os 5 trechos mais ligados à dificuldade escolhida e à questão, por palavras em comum (BM25), só entre os trechos da barreira associada (ex.: memória de trabalho).",
        "por_que_existe": "A orientação de adaptação precisa vir de fonte citável, não da memória do modelo.",
        "se_falhar": "Vêm trechos fora do assunto ou nenhum; sem trecho, o contexto não é montado e não há diretiva.",
    },
    "contexto_rag": {
        "nome": "Montagem do contexto",
        "macro": 7, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Junta num texto só a diretriz do nível escolhido, os conceitos que não podem mudar e os trechos numerados [T1]..[T5] com a referência (título, página, endereço), mais as regras de citação.",
        "por_que_existe": "Deixa cada afirmação da diretiva rastreável até um trecho e uma página.",
        "se_falhar": "Erro 'sem evidência não há diretiva' quando a busca vem vazia; ou o aviso de uso de um trecho se perde.",
    },
    "agente_estrategista": {
        "nome": "Agente Estrategista (não existe ainda)",
        "macro": 7, "agente": True, "dados_pessoais": False,
        "o_que_faz": "Deveria ler o contexto do RAG e escrever a diretiva psicopedagógica: como adaptar esta questão para esta dificuldade, com cada frase citando um trecho [T1]. Não está implementado no commit 65e1f09 (issue #16 aberta, PR #68).",
        "por_que_existe": "Liga a evidência dos documentos à adaptação; sem ele o Adaptador só segue a diretriz genérica do catálogo.",
        "se_falhar": "Hoje não existe: o Adaptador trabalha sem diretiva (na bancada, com a diretiva substituta).",
    },
    "diretiva_substituta_arnes": {
        "nome": "Diretiva substituta (bancada)",
        "macro": 7, "agente": True, "dados_pessoais": False,
        "o_que_faz": "Peça da bancada, não do grupo: no lugar do Estrategista, faz uma chamada ao modelo com as instruções do Estrategista do pacote RAG do grupo (gerar.INSTRUCOES) e o contexto montado.",
        "por_que_existe": "Permite exercitar o caminho completo, com diretiva chegando ao Adaptador, enquanto o Estrategista (#16) não existe.",
        "se_falhar": "Diretiva vazia ou sem citação; com o provedor determinístico ela sempre responde 'Não encontrei nos documentos...'.",
    },
    "conferencia_citacoes": {
        "nome": "Conferência das citações",
        "macro": 7, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Confere a diretiva de forma mecânica: quais [Tn] citou, se citou trecho que não existe e quais frases (de 4 palavras ou mais) ficaram sem citação. Não julga se o trecho sustenta a frase.",
        "por_que_existe": "Pega fonte inventada ou afirmação sem fonte antes de chegar ao Adaptador.",
        "se_falhar": "Uma diretiva com fonte inventada segue sem aviso; na bancada o resultado só é registrado, nada é bloqueado.",
    },
    "agente_adaptador": {
        "nome": "Agente Adaptador",
        "macro": 8, "agente": True, "dados_pessoais": False,
        "o_que_faz": "Agente de IA que reescreve a apresentação da questão para a dificuldade e o nível escolhidos (no nível 2: comandos encadeados viram lista de etapas com [ ]), mantendo palavras, ordem e conceitos. Toda saída passa pelo laudo de escopo; se reprovar ou o modelo falhar, entra a saída de reserva.",
        "por_que_existe": "É a entrega para o aluno: a mesma questão, com menos carga na memória de trabalho, sem facilitar o conteúdo.",
        "se_falhar": "O professor recebe o enunciado original sem mudança (reserva) ou, se o laudo não pegar, uma versão que muda o que é avaliado.",
    },
    "laudo_isolamento_escopo": {
        "nome": "Laudo de escopo",
        "macro": 8, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Compara o original com o adaptado: palavras perdidas ou novas, conceitos da trava ausentes, ordem e estrutura alteradas, conforme a regra da característica e do nível. Aprova ou reprova.",
        "por_que_existe": "Impede que a adaptação dê dica, resuma, troque palavra ou tire comando.",
        "se_falhar": "Uma adaptação que mudou o conteúdo é entregue como aprovada, ou uma adaptação boa é trocada pela reserva.",
    },
    "saida_de_reserva": {
        "nome": "Saída de reserva (sem IA)",
        "macro": 8, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Adaptação por regras, sem modelo: destaca os verbos de comando ou quebra a questão em etapas. Só existe para a característica de comandos múltiplos; nas outras devolve o enunciado original.",
        "por_que_existe": "Garante uma resposta segura quando o modelo falha ou sai do escopo.",
        "se_falhar": "O professor recebe o enunciado original sem adaptação, com a justificativa de que nada pôde ser garantido.",
    },
    "agente_auditor": {
        "nome": "Agente Auditor (não existe ainda)",
        "macro": 9, "agente": True, "dados_pessoais": False,
        "o_que_faz": "Deveria revisar a adaptação final (retenção de conceitos, TRCC) e devolvê-la ao Adaptador para refazer, no máximo 2 vezes (circuit breaker). Não está implementado no commit 65e1f09 (história 2.1.4, issue #19 aberta); só existe a métrica TRCC solta.",
        "por_que_existe": "Seria a segunda checagem, independente do Adaptador, antes de o texto chegar ao professor.",
        "se_falhar": "Hoje não existe: a única barreira é o laudo de escopo dentro do próprio Adaptador.",
    },
    "ciclo_rnf07": {
        "nome": "Tempo total da questão",
        "macro": 10, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Soma o tempo e os tokens das chamadas de IA da questão (Extrator + Adaptador) e compara com o limite do RNF-07: 15 s no nível 1, 40 s nos níveis 2 e 3.",
        "por_que_existe": "O professor não pode ficar esperando; mostra se a adaptação cabe no tempo prometido.",
        "se_falhar": "Marca dentro_do_limite=false; não bloqueia nada, só registra que demorou mais que o prometido.",
    },
    "agentes": {
        "nome": "Questão curta demais",
        "macro": None, "agente": False, "dados_pessoais": False,
        "o_que_faz": "Registro da bancada: a questão tem menos de 15 caracteres e o contrato dos agentes a recusaria, então eles não são chamados.",
        "por_que_existe": "Mostra quando uma questão foi pulada em vez de esconder o caso.",
        "se_falhar": "A questão aparece sem adaptação.",
    },
}

ORDEM_PADRAO = list(EXPLICACOES)


# ------------------------------------------------------------------ utilitários
def corta(s: Any, n: int) -> str:
    s = "" if s is None else (s if isinstance(s, str) else json.dumps(s, ensure_ascii=False))
    return s if len(s) <= n else s[: n - 1] + "…"


def ler_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def constante_texto(arquivo: Path, nome: str, subst: dict[str, str] | None = None) -> str | None:
    """Lê uma constante de texto (inclusive f-string simples) de um arquivo do grupo, sem importá-lo."""
    if not arquivo.exists():
        return None
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", None) == nome for t in no.targets):
            v = no.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
            if isinstance(v, ast.JoinedStr):
                partes = []
                for p in v.values:
                    if isinstance(p, ast.Constant):
                        partes.append(str(p.value))
                    elif isinstance(p, ast.FormattedValue) and isinstance(p.value, ast.Name):
                        partes.append((subst or {}).get(p.value.id, "{" + p.value.id + "}"))
                return "".join(partes)
    return None


def status_juntos(lst: list[str]) -> str:
    if not lst:
        return "ausente"
    cont: dict[str, int] = {}
    for s in lst:
        cont[s] = cont.get(s, 0) + 1
    if len(cont) == 1:
        return lst[0]
    return ", ".join(f"{k} ({v}/{len(lst)})" for k, v in cont.items())


# ------------------------------------------------------------------ redação dos trechos do RAG
def redigir_trechos(texto: str, fontes: list[dict]) -> str:
    """Troca cada bloco [Tn] (referência, aviso e texto do trecho) por um marcador com id e tamanho."""
    if not texto or not fontes:
        return texto
    inicios = []
    for f in fontes:
        cab = f"[{f['rotulo']}] {f.get('referencia', '')}"
        i = texto.find(cab)
        if i < 0:
            i = texto.find(f"[{f['rotulo']}] ")
        inicios.append((i, f))
    validos = sorted([(i, f) for i, f in inicios if i >= 0], key=lambda x: x[0])
    fim_trechos = texto.find("\n\nREGRAS DE CITAÇÃO")
    if fim_trechos < 0:
        fim_trechos = len(texto)
    saida, cursor = [], 0
    for k, (i, f) in enumerate(validos):
        fim = validos[k + 1][0] if k + 1 < len(validos) else fim_trechos
        bloco = texto[i:fim].rstrip("\n")
        n = len(f.get("trecho") or "")
        saida.append(texto[cursor:i])
        saida.append(f"[trecho {f['rotulo']}: {f['chunk_id']}, {n} caracteres]")
        cursor = i + len(bloco)
    saida.append(texto[cursor:])
    out = "".join(saida)
    for f in fontes:  # rede de segurança: trecho que ainda esteja no texto por outro caminho
        t = f.get("trecho") or ""
        if len(t) >= 50 and t in out:
            out = out.replace(t, f"[trecho {f['rotulo']}: {f['chunk_id']}, {len(t)} caracteres]")
    return out


# ------------------------------------------------------------------ exemplos legíveis por etapa
def fmt_exemplo(etapa: str, r: dict, ctx: dict) -> tuple[str, str]:
    e, s = r.get("entrada"), r.get("saida")
    if r.get("status") == "nao_implementada":
        return "(nenhuma: a etapa não existe no código)", r.get("resumo_saida", "")
    if etapa == "agentes":
        return "questão com menos de 15 caracteres", r.get("resumo_saida", "")
    if r.get("status") == "erro" and s is None:
        erro = r.get("erro") or {}
        return corta(e, LIM_EXEMPLO), corta(f"ERRO {erro.get('tipo')} {erro.get('codigo') or ''}: {erro.get('mensagem') or r.get('resumo_saida')}", LIM_EXEMPLO)
    if etapa == "upload_tamanho":
        return f"arquivo {e.get('arquivo')} ({e.get('bytes')} bytes)", f"{s} bytes aceitos (limite 10 MB)"
    if etapa == "extracao_documento":
        texto, fmt = (s or ["", "?"])[:2]
        return f"arquivo {e.get('arquivo')} ({e.get('bytes')})", corta(f"[formato {fmt}] {texto}", LIM_EXEMPLO)
    if etapa == "filtro_pii":
        texto, n = (s or ["", 0])[:2]
        return corta(e.get("texto"), LIM_EXEMPLO), corta(f"[{n} substituição(ões)] {texto}", LIM_EXEMPLO)
    if etapa == "validacao_conteudo":
        return f"texto filtrado com {e.get('caracteres')} caracteres", f"aceito: {s[0]} caracteres, {s[1]} palavras"
    if etapa == "decomposicao_estrutural":
        qs = [f"{q['id']} ({q['question_type']}, {len(q.get('options') or [])} alternativas): {corta(q['statement'], 110)}" for q in s.get("questions", [])]
        cx = [f"{c['id']} '{c.get('title')}' -> questões {c.get('target_questions')}" for c in s.get("context_blocks", [])]
        txt = (f"cabeçalho: {corta(s.get('header'), 80)} | textos de apoio: {cx or 'nenhum'} | questões: "
               + " || ".join(qs) + f" | não classificados: {len(s.get('unclassified_blocks', []))}")
        return corta(e.get("texto"), 300), corta(txt, LIM_EXEMPLO)
    if etapa == "organizacao_texto_corrido":
        nos = [f"{n['element_type']}: {corta(n['content'], 50)} ({len(n.get('children') or [])} filho(s))" for n in s.get("root_nodes", [])]
        return corta(e, 300), corta(f"título '{s.get('title')}'; {s.get('total_elements')} elementos, profundidade {s.get('max_depth')}; raiz: " + "; ".join(nos), LIM_EXEMPLO)
    if etapa == "selecao_caracteristicas":
        return (f"selected_ids={e.get('selected_ids')}",
                corta(f"{s.get('message')} ativadas={s.get('selected_ids')}; bloqueadas={s.get('blocked_count')}", LIM_EXEMPLO))
    if etapa == "perfil_pedagogico":
        return corta(e, LIM_EXEMPLO), corta(f"perfil válido (versão {s.get('versao_schema')}): {json.dumps(s, ensure_ascii=False)}", LIM_EXEMPLO)
    if etapa == "extrator_curricular":
        inv = s.get("invariants", {})
        tel = s.get("telemetry", {})
        return (corta(f"enunciado: {e.get('enunciado')} | disciplina: {e.get('disciplina')} | ano: {e.get('ano')}", LIM_EXEMPLO),
                corta(f"conceitos={inv.get('conceitos_obrigatorios')}; verbo={inv.get('verbo_comando_bncc')}; "
                      f"alerta='{inv.get('alerta_anti_muleta')}'; reserva usada={tel.get('used_fallback')}", LIM_EXEMPLO))
    if etapa == "busca_rag":
        tr = [f"{t['posicao']}. {t['chunk_id']} (doc {t['doc']}, p. {t.get('pagina')}, {len(t.get('trecho') or '')} caracteres, score {t.get('score')})"
              for t in s.get("trechos_rag", [])]
        return (corta(f"característica {e.get('id_caracteristica')}, nível {e.get('nivel')}, método {e.get('metodo')}, k={e.get('k')}; "
                      f"questão: {e.get('pergunta_adicional')}", LIM_EXEMPLO),
                corta(f"barreira {s.get('barreira_rag_associada')}, método efetivo {s.get('metodo_efetivo')}; trechos (texto omitido): " + "; ".join(tr), LIM_EXEMPLO))
    if etapa == "contexto_rag":
        fs = [f"{f['rotulo']}={f['chunk_id']} ({len(f.get('trecho') or '')} car.)" for f in s.get("fontes", [])]
        return (corta(f"resultado da busca_rag + invariantes {e.get('invariantes')}", LIM_EXEMPLO),
                corta(f"contexto de {len(s.get('contexto') or '')} caracteres (texto dos trechos omitido); fontes: " + "; ".join(fs), LIM_EXEMPLO))
    if etapa == "diretiva_substituta_arnes":
        p = (e or {}).get("prompt") or ""
        perg = p[p.find("PERGUNTA:"):] if "PERGUNTA:" in p else ""
        return corta(f"prompt de {len(p)} caracteres = contexto do RAG + {perg}", LIM_EXEMPLO), corta(s, LIM_EXEMPLO)
    if etapa == "conferencia_citacoes":
        return corta(f"diretiva: {e.get('diretiva')}", LIM_EXEMPLO), corta(
            f"citados={s.get('citados')}; inexistentes={s.get('citacoes_inexistentes')}; frases sem citação={s.get('frases_sem_citacao')}", LIM_EXEMPLO)
    if etapa == "agente_adaptador":
        esc, tel = s.get("escopo", {}), s.get("telemetry", {})
        return (corta(f"enunciado: {e.get('enunciado')} | característica {e.get('caracteristica')}, nível {e.get('nivel')}, com diretiva={e.get('tem_diretiva')}", LIM_EXEMPLO),
                corta(f"{s.get('texto_adaptado')} | adaptou={s.get('adaptacao_aplicada')}; laudo aprovado={esc.get('aprovado')}; "
                      f"reserva usada={tel.get('used_fallback')} ({tel.get('motivo_fallback')})", LIM_EXEMPLO))
    if etapa == "laudo_isolamento_escopo":
        return (corta(f"original: {e.get('original')} | adaptado: {e.get('adaptado')} | nível {e.get('nivel')}", LIM_EXEMPLO),
                corta(f"aprovado={s.get('aprovado')}; palavras perdidas={s.get('palavras_perdidas')}; novas={s.get('palavras_novas')}; "
                      f"conceitos perdidos={s.get('conceitos_perdidos')}; violações={s.get('violacoes')}", LIM_EXEMPLO))
    if etapa == "saida_de_reserva":
        texto, just = (s or ["", []])[:2]
        return corta(f"enunciado: {e.get('enunciado')} | nível {e.get('nivel')}", LIM_EXEMPLO), corta(f"{texto} | {just}", LIM_EXEMPLO)
    if etapa == "ciclo_rnf07":
        return f"telemetria das chamadas da questão, nível {e.get('nivel')}", corta(
            f"{s.get('chamadas')} chamadas, {s.get('total_ms')} ms, {s.get('total_tokens')} tokens; limite {s.get('limite_ms')} ms; dentro={s.get('dentro_do_limite')}", LIM_EXEMPLO)
    return corta(e, LIM_EXEMPLO), corta(s if s is not None else r.get("resumo_saida"), LIM_EXEMPLO)


# ------------------------------------------------------------------ chamadas ao modelo (estilo Langfuse)
def chamadas_do_run(linhas: list[dict], sis_extrator: str | None, sis_adaptador: str | None,
                    sis_estrategista: str | None) -> list[dict]:
    """Uma chamada por linha com tokens (o ClienteRastreado soma os tokens na etapa aberta).

    O rastro grava o prompt bruto só na diretiva substituta; para Extrator e Adaptador o prompt é
    reconstruído com os mesmos passos de _montar_prompt_usuario do grupo, a partir das entradas e saídas
    gravadas no rastro (marcado em 'prompt_origem').
    """
    out = []
    por_q: dict[Any, dict[str, dict]] = {}
    for r in linhas:
        por_q.setdefault(r.get("questao"), {})[r["etapa"]] = r
    for r in linhas:
        if not (r.get("tokens_entrada") or r.get("tokens_saida") or r.get("modelo")):
            continue
        etapa, q = r["etapa"], por_q.get(r.get("questao"), {})
        e, s = r.get("entrada") or {}, r.get("saida")
        prompt: Any = None
        saida: Any = None
        origem_p = origem_s = ""
        fontes = ((q.get("contexto_rag") or {}).get("saida") or {}).get("fontes") or []
        if etapa == "extrator_curricular":
            partes = []
            if e.get("disciplina"):
                partes.append(f"DISCIPLINA: {e['disciplina']}")
            if e.get("ano"):
                partes.append(f"ANO/ETAPA: {e['ano']}")
            partes.append(f"ENUNCIADO:\n{e.get('enunciado', '')}")
            prompt = {"sistema": sis_extrator or "a confirmar", "usuario": "\n".join(partes)}
            origem_p = "reconstruído: SYSTEM_PROMPT_EXTRATOR do grupo + _montar_prompt_usuario com a entrada gravada"
            inv = (s or {}).get("invariants")
            saida = json.dumps(inv, ensure_ascii=False) if inv is not None else None
            origem_s = "invariantes interpretados pelo agente (o rastro não guarda a resposta bruta; no provedor eco ela é este mesmo JSON)"
        elif etapa == "agente_adaptador":
            busca = ((q.get("busca_rag") or {}).get("saida") or {})
            d = busca.get("diretriz_andaime") or {}
            inv = (((q.get("extrator_curricular") or {}).get("saida") or {}).get("invariants")) or {}
            diretiva = (q.get("diretiva_substituta_arnes") or {}).get("saida")
            if d and inv:
                partes = [
                    f"CARACTERÍSTICA FUNCIONAL: {e.get('caracteristica')}",
                    f"NÍVEL {e.get('nivel')}: {d.get('rotulo')}",
                    f"OBJETIVO DO ANDAIME: {d.get('objetivo_andaime')}",
                    "AÇÕES PERMITIDAS:\n" + "\n".join(f"- {a}" for a in d.get("acoes_permitidas", [])),
                    "RESTRIÇÕES DE ESCOPO:\n" + "\n".join(f"- {x}" for x in d.get("restricoes_escopo", [])),
                    f"CONCEITOS OBRIGATÓRIOS: {inv.get('conceitos_obrigatorios')}",
                    f"TERMOS INTOCÁVEIS: {inv.get('termos_tecnicos_intocaveis')}",
                ]
                if inv.get("alerta_anti_muleta"):
                    partes.append(f"ALERTA ANTI-MULETA: {inv['alerta_anti_muleta']}")
                if diretiva:
                    partes.append(f"DIRETIVA PSICOPEDAGÓGICA:\n{diretiva}")
                partes.append(f"ENUNCIADO ORIGINAL:\n{e.get('enunciado', '')}")
                usuario = redigir_trechos("\n".join(partes), fontes)
                origem_p = "reconstruído: SYSTEM_PROMPT_ADAPTADOR do grupo + _montar_prompt_usuario com diretriz, invariantes e diretiva gravados no rastro"
            else:
                usuario = f"a confirmar (faltam diretriz/invariantes no rastro); enunciado: {e.get('enunciado', '')}"
                origem_p = "a confirmar"
            prompt = {"sistema": sis_adaptador or "a confirmar", "usuario": usuario}
            tel = (s or {}).get("telemetry") or {}
            if s and not tel.get("used_fallback"):
                saida = json.dumps({"texto_adaptado": s.get("texto_adaptado"), "justificativas": s.get("justificativas")}, ensure_ascii=False)
                origem_s = "campos interpretados pelo agente (o rastro não guarda a resposta bruta; no provedor eco ela é este mesmo JSON)"
            else:
                saida = json.dumps(s, ensure_ascii=False) if s else None
                origem_s = "a confirmar: houve reserva, a saída final não é a resposta do modelo"
        elif etapa == "diretiva_substituta_arnes":
            prompt = {"sistema": sis_estrategista or "a confirmar", "usuario": redigir_trechos(e.get("prompt") or "", fontes)}
            origem_p = "gravado no rastro (entrada.prompt) com o texto dos trechos do RAG substituído por marcador; sistema = gerar.INSTRUCOES do grupo"
            saida = redigir_trechos(s or "", fontes) if isinstance(s, str) else s
            origem_s = "resposta do modelo gravada no rastro"
        else:
            prompt = corta(e, LIM_PROMPT)
            saida = s
            origem_p = origem_s = "entrada/saída da etapa"
        if isinstance(prompt, dict):  # até 4000 caracteres no total, preservando o pedido do usuário
            u = corta(prompt["usuario"], LIM_PROMPT - 200)
            prompt = {"sistema": corta(prompt["sistema"], max(200, LIM_PROMPT - len(u))), "usuario": u}
        out.append({
            "run_id": r["run_id"], "material": r["material_id"], "questao": r.get("questao"), "etapa": etapa,
            "agente": EXPLICACOES.get(etapa, {}).get("nome", etapa),
            "modelo": r.get("modelo"), "provedor": r.get("provedor"),
            "prompt": prompt, "saida": corta(saida, LIM_SAIDA),
            "tokens_entrada": r.get("tokens_entrada", 0), "tokens_saida": r.get("tokens_saida", 0),
            "latencia_s": r.get("latencia_s"), "status": r.get("status"), "erro": r.get("erro"),
            "prompt_origem": origem_p, "saida_origem": origem_s,
        })
    return out


# ------------------------------------------------------------------ teste de licença
def textos_chunks() -> str:
    partes = []
    for l in CHUNKS.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        d = json.loads(l)
        for v in d.values():
            if isinstance(v, str) and len(v) >= JANELA:
                partes.append(v)
    return "\x00".join(partes)


def strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def procurar_copias(dados: Any, corpus: str) -> list[str]:
    """Toda cópia de 200+ caracteres contém uma janela de 100 alinhada; acha candidatas e mede a extensão real."""
    meio = JANELA // 2
    achados = []
    for s in strings(dados):
        if len(s) < JANELA:
            continue
        for p in range(0, len(s) - meio + 1, meio):
            w = s[p:p + meio]
            i = corpus.find(w)
            while i >= 0:
                esq = 0
                while p - esq - 1 >= 0 and i - esq - 1 >= 0 and s[p - esq - 1] == corpus[i - esq - 1]:
                    esq += 1
                dir_ = meio
                while p + dir_ < len(s) and i + dir_ < len(corpus) and s[p + dir_] == corpus[i + dir_]:
                    dir_ += 1
                if esq + dir_ >= JANELA:
                    achados.append(s[p - esq:p + dir_][:120])
                    break
                i = corpus.find(w, i + 1)
    return achados


# ------------------------------------------------------------------ principal
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grupo", default=GRUPO_PADRAO, help="clone do repositório do grupo (só leitura)")
    ap.add_argument("--saida", default=str(OUTPUTS / "31-etapas.json"))
    args = ap.parse_args(argv)
    grupo = Path(args.grupo)

    resumo = json.loads((OUTPUTS / "26-rastro-pipeline-resumo.json").read_text(encoding="utf-8"))
    mapa = json.loads((OUTPUTS / "27-mapa-codigo.json").read_text(encoding="utf-8"))
    macros = {m["ordem"]: m for m in mapa.get("etapas_pipeline", [])}

    agentes_dir = grupo / "backend" / "src" / "iris" / "agents"
    sis_ext = constante_texto(agentes_dir / "curriculum_extractor.py", "SYSTEM_PROMPT_EXTRATOR")
    sis_ada = constante_texto(agentes_dir / "adapter_agent.py", "SYSTEM_PROMPT_ADAPTADOR")
    gerar = grupo / "rag" / "iris-rag" / "pacote" / "gerar.py"
    frase = constante_texto(gerar, "FRASE_SEM_RESPOSTA") or ""
    sis_est = constante_texto(gerar, "INSTRUCOES", {"FRASE_SEM_RESPOSTA": frase})

    # runs principais: o mais recente de cada material, como está no resumo 26
    runs: list[tuple[str, list[dict]]] = []
    faltando = []
    for ex in resumo["execucoes"]:
        p = REPORTS / f"{ex['run_id']}.jsonl"
        if p.exists():
            runs.append((ex["material_id"], ler_jsonl(p)))
        else:
            faltando.append(ex["run_id"])
    if not runs:
        print(f"nenhum rastro encontrado em {REPORTS}; rode antes: make rastro-pipeline", file=sys.stderr)
        return 1

    vistos = {r["etapa"] for _, ls in runs for r in ls}
    ordem = [e for e in ORDEM_PADRAO if e in vistos] + sorted(vistos - set(ORDEM_PADRAO))

    # etapas que só aparecem nos casos adversariais (ex.: saida_de_reserva, entrada_texto): run adv mais recente
    extras: dict[str, tuple[str, list[dict]]] = {}
    for p in sorted(REPORTS.glob("adv-*.jsonl"), reverse=True):
        ls = ler_jsonl(p)
        for r in ls:
            if r["etapa"] in EXPLICACOES and r["etapa"] not in vistos and r["etapa"] not in extras:
                extras[r["etapa"]] = (r["material_id"], ls)
    for e in ORDEM_PADRAO:
        if e in extras and e not in ordem:
            # insere logo depois da etapa vizinha na ordem padrão
            ant = [x for x in ORDEM_PADRAO[:ORDEM_PADRAO.index(e)] if x in ordem]
            ordem.insert(ordem.index(ant[-1]) + 1 if ant else 0, e)

    etapas = []
    for nome in ordem:
        ex = EXPLICACOES.get(nome, {"nome": nome, "macro": None, "agente": False, "dados_pessoais": False,
                                    "o_que_faz": "a confirmar", "por_que_existe": "a confirmar", "se_falhar": "a confirmar"})
        fontes_runs = runs if nome in vistos else [extras[nome]]
        status_mat: dict[str, str] = {}
        candidatos = []
        for mat, ls in fontes_runs:
            st = [r["status"] for r in ls if r["etapa"] == nome]
            status_mat[mat] = status_juntos(st)
            candidatos += [(r, ls) for r in ls if r["etapa"] == nome]
        # exemplo: primeira ocorrência com status ok (senão a primeira); filtro_pii prefere a que trocou algo
        preferido = [c for c in candidatos if c[0]["status"] == "ok"] or candidatos
        if nome == "filtro_pii":
            com_troca = [c for c in preferido if isinstance(c[0].get("saida"), list) and c[0]["saida"][1]]
            preferido = com_troca or preferido
        r, ls = preferido[0]
        fontes_q = next(((x.get("saida") or {}).get("fontes") or [] for x in ls
                         if x["etapa"] == "contexto_rag" and x.get("questao") == r.get("questao")), [])
        ent, sai = fmt_exemplo(nome, r, {})
        ent, sai = redigir_trechos(ent, fontes_q), redigir_trechos(sai, fontes_q)
        funcao = r.get("funcao")
        if r["status"] == "nao_implementada":
            funcao = "nao_implementada"
        macro = ex["macro"]
        etapas.append({
            "etapa": nome,
            "nome": ex["nome"],
            "macro": macro,
            "macro_etapa": macros.get(macro, {}).get("etapa") if macro else None,
            "macro_status": macros.get(macro, {}).get("status") if macro else None,
            "funcao": funcao,
            "agente": ex["agente"],
            "o_que_faz": ex["o_que_faz"],
            "por_que_existe": ex["por_que_existe"],
            "se_falhar": ex["se_falhar"],
            "dados_pessoais": ex["dados_pessoais"],
            "exemplo": {
                "material": r["material_id"], "questao": r.get("questao"),
                "entrada": ent, "saida": sai,
                "latencia_s": r.get("latencia_s"), "status": r.get("status"),
                "run_id": r["run_id"],
            },
            "status_por_material": status_mat,
        })

    chamadas = []
    for _, ls in runs:
        chamadas += chamadas_do_run(ls, sis_ext, sis_ada, sis_est)

    dados = {
        "gerado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "commit_grupo": resumo.get("commit_grupo"),
        "provedor": resumo.get("provedor"),
        "modelo": resumo.get("modelo"),
        "aviso": resumo.get("aviso"),
        "fonte": {"resumo": "outputs/26-rastro-pipeline-resumo.json", "runs": [ls[0]["run_id"] for _, ls in runs],
                  "runs_adversariais_usados": sorted({ls[0]["run_id"] for _, ls in extras.values()}),
                  "runs_ausentes": faltando,
                  "nota": ("texto dos trechos do RAG omitido (licenças restritas); prompts do Extrator e do Adaptador "
                           "reconstruídos a partir do código do grupo e do rastro, porque o rastro só grava o prompt bruto da diretiva")},
        "etapas": etapas,
        "chamadas": chamadas,
    }

    # teste: nenhum pedaço de 200+ caracteres de trecho do RAG no arquivo versionado
    if not CHUNKS.exists():
        print(f"chunks.jsonl ausente em {CHUNKS}: não dá para conferir licença; abortando", file=sys.stderr)
        return 1
    copias = procurar_copias(dados, textos_chunks())
    if copias:
        print(f"FALHOU: {len(copias)} trecho(s) do RAG com {JANELA}+ caracteres no JSON; nada gravado:", file=sys.stderr)
        for c in copias[:5]:
            print("   ", repr(c), file=sys.stderr)
        return 1

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"{len(etapas)} etapas, {len(chamadas)} chamadas de modelo ({len(runs)} materiais; provedor {dados['provedor']})")
    for e in etapas:
        marca = "agente" if e["agente"] else "      "
        print(f"  {str(e['macro'] or '-'):>2} {marca} {e['etapa']:<28} {', '.join(f'{k}={v}' for k, v in e['status_por_material'].items())}")
    print(f"teste de licença: nenhuma sequência de {JANELA}+ caracteres do chunks.jsonl no arquivo")
    print(f"gravado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
