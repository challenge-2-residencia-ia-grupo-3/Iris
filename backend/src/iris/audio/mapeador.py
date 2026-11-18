"""Mapeador de fala docente para características funcionais do catálogo (RF-05).

Funciona sobre o TEXTO já transcrito e sanitizado, localmente e sem modelo de linguagem: cada característica
tem uma lista de formas como professores descrevem aquele comportamento em sala ("responde só a primeira parte",
"se perde no meio do cálculo", "demora para começar"). A sugestão é explicável: devolve a pontuação e os trechos
exatos da fala que a motivaram, para o professor conferir. O professor sempre confirma ou desmarca (HITL).

Só comportamento observável pontua: rótulos diagnósticos e medicação não estão no léxico (RNF-03) e uma fala com
"TDAH" ou "laudo" não ganha sugestão por causa disso. Característica nova no catálogo sem léxico próprio cai num
modo de reserva que usa só as `palavras_chave_busca` dela (peso menor).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

LIMIAR = 2          # soma mínima para sugerir (um gatilho forte = 2; dois fracos = 2)
LIMITE_SUGESTOES = 4
PESO_FORTE, PESO_FRACO = 2, 1

# Cada item: "padrão" (peso forte) ou ("padrão", peso). Espaço = qualquer separador; sem acentos, minúsculas.
# Termina com "*" = prefixo (ex.: "afobad*" cobre afobado/afobada).
Gatilho = str | tuple[str, int]

LEXICO: dict[str, list[Gatilho]] = {
    "sobrecarga_memoria_trabalho_comandos_multiplos": [
        r"(responde|resolve|faz|fez|respondeu) (so|apenas|somente) (a |o )?(primeira|1a|1) (parte|pergunta|questao|coisa|instrucao|comando)",
        r"esquece (de )?(responder|fazer|resolver) (a |o )?(segunda|terceira|outra|ultima|resto)",
        r"(varios|muitos|dois ou mais|mais de um|mais de uma) (comandos|verbos|instrucoes|pedidos)",
        r"(pede|pedem|pedindo) (varias|duas|tres|mais de uma) coisas",
        r"perde o fio (da|do|de) (instrucao|enunciado|comando|pergunta|questao)",
        r"(deixa|omite|esquece) (parte|partes|itens|etapas) (da|de) (resposta|questao)",
        r"nao (responde|faz|resolve) (tudo|todas as partes|todos os itens)",
        r"(enunciado|questao|pergunta)s? (com )?(varios|muitos) (itens|passos|comandos)",
        r"(multiplos|varios) comandos",
        r"(faz|resolve|responde|cumpre|executa|fez) (so|apenas|somente) (uma|um|a primeira|o primeiro)( delas| deles)?,? (e )?(esquece|deixa|se perde|ignora|larga)",
        r"faz a primeira e (se )?(perde|esquece|deixa|ignora)",
        r"esquece (as |os )?(outras|outros|demais|restante|resto)",
        r"(varias|muitas|duas|tres|mais de uma) (perguntas|tarefas|coisas|instrucoes|ordens) (juntas|de uma vez|ao mesmo tempo|numa so|em uma so)",
        r"(varias|muitas) tarefas de uma vez",
    ],
    "retencao_dados_intermediarios_problemas_multietapas": [
        r"esquece (a |o |as |os )?(unidade|unidades|dados|dado|valores|valor|numeros|numero|condicao|condicoes|premissas)",
        r"perde (os |as |o |a )?(valores|numeros|dados|resultados|contas)( parciais| intermediarios| do meio)?",
        r"(se )?perde (no meio|nas etapas|na metade) (do|de|da) (calculo|problema|conta|resolucao)",
        r"troca (os )?numeros",
        r"problemas? (de|com) (varias|muitas|multiplas) etapas",
        r"(problemas?|questoes|contas) (de|com) (varios|muitos) passos",
        r"nao (lembra|guarda|retem|segura) (os )?(dados|valores|numeros|resultados)",
        r"(resultado|resultados|valores) (parcial|parciais|intermediario|intermediarios)",
        r"(esquece|perde) (o que )?(o )?(enunciado|problema|texto) (disse|deu|informou|pedia)",
        r"(problemas?|questoes|exercicios) (com|de|que tem|que tem) (varias|muitas|diversas) (contas|operacoes|etapas|passos)",
        r"(esquece|perde|nao lembra) (o )?(resultado|valor|numero) (da |de |do )?(conta|etapa|passo|operacao|calculo) (anterior|de antes|passad\w*)",
        r"(precisa|exige|tem|pede)( de)? (mais de um|varios|muitos|dois ou mais) (passo|passos|etapa|etapas)",
        r"perde o que (ja )?(tinha |havia )?(calculado|feito|resolvido|encontrado|achado)",
        r"se (embola|enrola|confunde) (na|no|com) (conta|calculo|resolucao|problema|etapas)",
    ],
    "atencao_sustentada_textos_longos": [
        r"textos? (muito |bem |bastante )?(longos?|extensos?|grandes?|compridos?|densos?)",
        r"(nao|nunca) (termina|consegue terminar|chega ao fim) (de ler|a leitura|o texto|do texto)",
        r"(pula|salta|vai) (direto )?(para|pra|pras|pro|ate) (as )?alternativas",
        r"(perde|perdeu) a linha",
        r"abandona (a )?leitura",
        r"(desiste|desistiu) (de ler|da leitura)",
        r"(se )?(cansa|desconcentra|dispersa) (de|ao|na|durante a) (ler|leitura)",
        r"(pula|salta) linhas",
        r"(nao )?(aguenta|suporta|da conta de|tem paciencia para) (ler|a leitura de|leituras? de) (um |o |os |textos? )",
        r"chuta (as )?alternativas",
        r"(na metade|no meio|no comeco) (do|da) (texto|leitura) (ja )?(desiste|desistiu|dispersa|se distrai|olha para o lado|olhando para o lado)",
        ("olhando (pro|para o) lado", PESO_FRACO),
        r"(nao )?(consegue|aguenta) (ficar |se manter |permanecer )?(concentrad\w*|atent\w*|focad\w*) ate o (fim|final)",
        r"textos? (que )?(passa|passam|ultrapassa\w*|tem|com) (de )?(mais de )?(uma|1|duas|varias) pagina",
        r"(le|leu) (so )?o primeiro paragrafo e (depois )?(desiste|desistiu|para|abandona|se distrai|dispersa)",
    ],
    "distratibilidade_poluicao_visual_layout": [
        r"(se )?(distrai|distraem|distraiu|desvia o foco|desvia a atencao|se prende) (com|por|em|nas|nos|a) (as |os |nas |nos )?(figuras|imagens|desenhos|caixas|cores|enfeites|ilustracoes|detalhes decorativos|decoracao)",
        r"(muita|muitas|muito|muitos|excesso de) (informacao|informacoes|coisa|coisas|imagem|imagens|figura|figuras|cor|cores|estimulo|estimulos) (na|em|por) (pagina|folha|prova|tela|atividade)",
        r"(layout|pagina|folha|prova|atividade) (muito |bem )?(poluida|poluido|confusa|confuso|carregada|carregado|bagun\w*|cheia|cheio)",
        r"polui\w* visual",
        r"(varias|diferentes|muitas) fontes",
        r"alternativas? (em|nas?) (varias |multiplas |duas )?colunas",
        r"(caixas?|quadros?|boxes?) (laterais|decorativ\w*)",
        r"(desenho|desenhos|figura|figuras|imagem|imagens|ilustracao|ilustracoes|cores|barulho|movimento) (chama|chamam|prende|prendem|tira|tiram|rouba|roubam) (a |o )?(atencao|foco)",
        r"(fica olhando|so olha|presta atencao (so )?(em|na|nas|nos)|olha so) (a |as |o |os )?(figuras?|imagens?|desenhos?|ilustracoes|cores)",
        r"(esquece|perde) (da|a|o) (pergunta|enunciado|questao) (por causa|com) (da|das|do|dos) (figura|figuras|imagem|imagens|desenho|desenhos)",
    ],
    "impulsividade_leitura_superficial_negacoes": [
        r"(ignora|ignorou|nao le|nao percebe|nao ve|esquece|passa batido) (a |as |o |os )?(palavra |palavras |termo |termos )?(nao|negacao|negacoes|excecao|excecoes|exceto|incorreta|errada)",
        r"questoes? (com|de|que pedem|que pede) (nao|excecao|exceto|incorreta|negacao)",
        r"(responde|marca|respondeu|marcou) (rapido|rapidamente|afobado|apressado|precipitado|sem pensar|no impulso)",
        r"(responde|marca|respondeu|marcou) (antes de|sem) (ler|terminar de ler|ler ate o fim|ler tudo|ler direito)",
        r"le (so|apenas|somente) (o comeco|as primeiras palavras|a primeira linha|o inicio|a primeira parte)",
        r"(pressa|correria) (na|ao) (leitura|ler|prova)",
        r"leitura (superficial|apressada)",
        r"(le|leu|olha|viu) (so )?(a )?(primeira|1a|1) (frase|linha|palavra|parte) e (ja )?(responde|marca|respondeu|marcou|chuta)",
        r"(nem|nao) (ve|viu|percebe|percebeu|nota|notou|repara|reparou) (que )?(a )?(questao|pergunta|enunciado|ela|o enunciado) (pedia|pede|era|queria|mandava)",
        r"(nao|nem) (le|leu) (o enunciado |a questao |a pergunta )?(ate o fim|inteir[oa]|todo|toda|direito)",
        ("afobad*", PESO_FRACO), ("apressad*", PESO_FRACO), ("precipitad*", PESO_FRACO), ("impulsiv*", PESO_FRACO),
        ("(alternativa|questao) (incorreta|errada)", PESO_FRACO), ("exceto", PESO_FRACO),
        r"(marca|escolhe|assinala|responde) a primeira (alternativa|opcao|que (parece|ve))",
        r"sem ler as (outras|demais|alternativas|opcoes)",
r"(erra|errou|erram) (as |os )?(perguntas|questoes|itens)( com| que tem| que pedem)?( a palavra)? (nao|exceto)",
        r"cai (nas|em) pegadinhas?",
        r"(responde|marca|faz|respondeu|fez) (correndo|de qualquer jeito|no automatico|voando)",
    ],
    "organizacao_sequencial_expressao_escrita": [
        r"(sabe|explica|fala|responde) (bem )?(oralmente|falando|de forma oral|na fala|em voz alta)",
        r"(dificuldade|dificuldades) (para|em|de) (organizar|ordenar|estruturar|sequenciar|planejar) (a |as |o |os )?(escrita|redacao|resposta|respostas|ideias|texto|paragrafos?)",
        r"(nao )?(consegue|sabe) (organizar|ordenar|estruturar) (a |as |o |os )?(escrita|redacao|resposta|respostas|ideias|texto)",
        r"(questoes|respostas|perguntas|provas|atividades) discursivas",
        r"comeco meio e fim",
        r"(escreve|redige|escreveu) (de forma |de modo )?(desorganizad\w*|confus\w*|telegrafic\w*|fora de ordem|sem sequencia)",
        r"ideias (soltas|desordenadas|misturadas|embaralhadas|fora de ordem)",
        r"(respostas?|textos?) (telegrafic\w*|curt\w* demais|sem justificativa)",
        r"(inverte|troca) a (ordem|sequencia) (dos|de) passos",
        r"(nao )?(consegue|sabe) (colocar|passar) (no papel|para o papel|pra escrita)",
        r"(quando|na hora de|ao) escrev\w* (a resposta )?(fica|sai|vira|ficam|saem) (tudo )?(embaralhad\w*|bagunc\w*|confus\w*|desorganizad\w*|fora de ordem)",
        r"ideias (saem|ficam|vem) (fora de ordem|embaralhadas|soltas|misturadas|desorganizadas|desordenadas)",
        r"(nao )?(sabe|consegue) (montar|construir|estruturar|organizar) (o |a )?(texto|resposta|redacao|paragrafo)",
        ("(explica|fala|conta) (tudo |muito bem |direitinho )?(falando|oralmente|de boca)", PESO_FRACO),
    ],
    "fadiga_executiva_autorregulacao_provas_extensas": [
        r"(se )?(cansa|cansou|esgota|esgotou|desanima|desanimou) (no meio|ao longo|durante|no final|na metade|perto do fim|depois) (da|de|do) (prova|avaliacao|teste|atividade)",
        r"(prova|provas|avaliacao|avaliacoes|teste|testes) (muito |bem )?(longa|longas|extensa|extensas|comprida|compridas|demorada|demoradas)",
        r"(comeca|comecou|inicia) bem (e |mas )?(depois |no final |com o tempo )?(piora|cai|desanima|cansa|erra|desorganiza)",
        r"(chuta|chutou|responde aleatoriamente|marca qualquer) (no final|as ultimas|nas ultimas|no fim)",
        r"(erra|errou) (questoes )?(simples|faceis) (no final|no fim|nas ultimas)",
        r"(rendimento|desempenho) (cai|caiu|diminui|piora|despenca)",
        r"(ultimas|final) (questoes|da prova) (em branco|sem responder|no chute)",
        r"nao (percebe|sabe|tem nocao) (quanto|o quanto) falta",
        r"(depois|aos poucos|com o tempo|mais pro final) (vai |ele vai |ela vai |vao )?(desanimando|cansando|se cansando|perdendo o ritmo|perdendo o foco|caindo|piorando)",
        r"(ultimas|finais|ultimos) (questoes|perguntas|itens)( ele| ela)? (deixa|deixou|chuta|chutou|nao faz|nao fez|nao responde|nao respondeu)",
        r"(na|nas) (segunda|ultima) (metade|parte) (da|de) (prova|avaliacao) (vai|fica|rende) (mal|pior|cansad\w*|desanimad\w*)",
        ("desanimando", PESO_FRACO), ("deixa em branco", PESO_FRACO),
        ("exaust*", PESO_FRACO), ("esgotament*", PESO_FRACO), ("esgotad*", PESO_FRACO),
        (r"ansios[oa]s? (durante|na|nas|em) (prova|provas|avaliacao|avaliacoes)", PESO_FRACO),
        r"(nao )?aguenta mais",
        r"entrega (tudo )?(no chute|chutando|em branco)",
        r"(na|nas) (segunda|ultima|final)\w* (parte|metade|etapa)( da)? (prova|avaliacao|teste)",
        r"(pela|na) metade (ja )?(esta|fica|ficou|estava) (exaust\w*|cansad\w*|esgotad\w*|sem energia)",
    ],
    "flexibilidade_cognitiva_alternancia_topicos": [
        r"(mudanca|mudancas|muda|mudam|troca|trocam|alternancia|alternar) (brusca |bruscas |repentina )?(de |do |da |dos |entre )(assunto|assuntos|tema|temas|formato|tipo|tipos|topico|topicos|regra|regras)",
        r"(continua|continuou|segue|insiste) (usando|aplicando|somando|multiplicando|com) (a )?(mesma )?(regra|formula|logica|conta|operacao|raciocinio) (da |de |do )?(questao |conta )?(anterior|passada|de antes)",
        r"(nao )?(consegue|sabe) (mudar|trocar|alternar|migrar) (de )?(assunto|tema|raciocinio|regra|formato|topico)",
        r"(preso|presa|travado|travada|agarrado|agarrada) (na|a|em) (questao|regra|logica|formula) anterior",
        r"(prova|provas|atividade|atividades|avaliacao) (mistura|misturam) (questoes|temas|assuntos|tipos)",
        r"sem aviso de transicao",
        r"(aplica|usou|usa) (o )?(contexto|texto|regra) (do )?(texto|questao) (1|um|anterior)",
        r"rigidez (cognitiva|mental|de pensamento)",
        r"(fica|continua|segue|ficou) (preso|presa|agarrado|agarrada) (no|ao|a|em) (jeito|modo|metodo|raciocinio|forma) (de|do) (resolver|pensar|fazer)",
        r"(mesmo )?(quando|mesmo que) (o|a) (tipo de )?(exercicio|questao|assunto|atividade|tema|conteudo) (muda|mudou|troca|trocou)",
        r"demora (a|para|pra) (se )?(ajustar|adaptar|acostumar) (quando|a|com) (a |o )?(muda\w*|troca\w*|novo (assunto|tema|formato))",
    ],
    "bloqueio_iniciacao_tarefas_abertas": [
        r"(nao )?(consegue|sabe|tem iniciativa para) (comecar|iniciar|dar o primeiro passo|dar partida)",
        r"demora (muito |bastante |demais )?(para|pra|a) (comecar|iniciar|dar o primeiro passo)",
        r"(folha|pagina|prova|questao|caderno) em branco",
        r"(fica|ficou|permanece) (parad[oa]|travad[oa]|paralisad[oa]|olhando para a (folha|questao|prova))",
        r"nao sabe por onde (comecar|iniciar|ir)",
        r"(trava|bloqueia|paralisa|congela) (diante|na frente|ao ver|quando ve|com) (de )?(as |uma |um )?(questoes |questao |perguntas |atividades |tarefas )?(abertas?|discursivas?|livres?)",
        r"(primeiro passo|ponto de partida|pergunta guia)",
        r"(so |apenas )?(comeca|consegue comecar) (depois que|quando) (eu |o professor |a professora )?(indico|indica|ajudo|ajuda|dou|da|mostro|mostra) (por onde|a primeira|o primeiro|um exemplo)",
        ("(questoes|perguntas|atividades|tarefas) (abertas|livres)", PESO_FRACO),
        r"nao sabe (como|o que fazer para|de que jeito) (comecar|iniciar)",
        r"(enrola|enrolando|adia|adiando|empurra) (para|pra|a hora de|o) ?(comecar|iniciar|inicio)",
        r"(atividades?|tarefas?|questoes) (livres?|sem (um )?modelo|sem (um )?exemplo)",
        r"nem (escreve|faz) (a )?primeira (linha|frase|palavra)",
    ],
    "ritmo_processamento_pressao_temporal": [
        r"(sob|com|na|por|diante da|devido a) pressao (de|do|por) (tempo|prazo|relogio|cronometro)",
        r"(tempo|cronometro|relogio|prazo) (curto|apertado|acabando|limitado|contado|correndo)",
        r"(frases|enunciados?|periodos) (muito |bem |bastante )?(longas?|compridas?|extensas?|complexas?|rebuscad\w*)",
        r"(precisa|precisaria|necessita|depende) de (mais tempo|tempo extra|tempo adicional|tempo a mais)",
        r"(acerta|consegue|resolve|vai bem|vai melhor|rende) (quando|se|com) (tem |tiver |recebe |ganha )?(mais |bastante )?(tempo|calma)",
        r"(demora|lento|lenta|lentidao) (para|na|ao|em) (ler|leitura|decodificar|interpretar|processar|entender o enunciado)",
        r"(nao )?(termina|consegue terminar|conclui|consegue concluir) (a prova|as ultimas|as questoes finais|no tempo|dentro do tempo)",
        r"voz passiva",
        ("decodific*", PESO_FRACO), ("velocidade de processamento", PESO_FRACO), ("processamento lento", PESO_FRACO),
        r"(quando|se) (eu )?(cronometro|marco o tempo|limito o tempo|coloco tempo)",
        r"(fica|ficou|fica muito) nervos\w* (com|por causa d\w*) (o )?(tempo|cronometro|relogio|prazo)",
        r"(a )?(prova|o tempo) acaba (antes de|sem) (ele |ela )?(terminar|concluir|conseguir)",
        r"(mais )?lent[oa] (para|na|ao|em) (ler|leitura|escrever|resolver)",
    ],
}


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e pontuação virando espaço, MANTENDO o comprimento (para citar o trecho original)."""
    saida: list[str] = []
    for ch in unicodedata.normalize("NFC", texto):
        base = unicodedata.normalize("NFD", ch)[0]
        base = base.lower()
        if len(base) != 1:
            base = " "
        saida.append(base if (base.isalnum() or base.isspace()) else " ")
    return "".join(saida)


def _compilar(padrao: str) -> re.Pattern[str]:
    prefixo = padrao.endswith("*")
    corpo = padrao[:-1] if prefixo else padrao
    corpo = corpo.replace(" ", r"\s+")
    return re.compile(r"\b" + corpo + ("" if prefixo else r"\b"))


_COMPILADO: dict[str, list[tuple[re.Pattern[str], int]]] = {
    cid: [(_compilar(g if isinstance(g, str) else g[0]), PESO_FORTE if isinstance(g, str) else g[1]) for g in itens]
    for cid, itens in LEXICO.items()
}


@dataclass(frozen=True)
class Sugestao:
    id_caracteristica: str
    nome: str
    pontuacao: int
    confianca: str
    evidencias: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_caracteristica": self.id_caracteristica,
            "nome": self.nome,
            "pontuacao": self.pontuacao,
            "confianca": self.confianca,
            "evidencias": list(self.evidencias),
        }


def _pontuar(texto: str, base: str, padroes: list[tuple[re.Pattern[str], int]]) -> tuple[int, list[str]]:
    total, trechos, vistos = 0, [], set()
    for padrao, peso in padroes:
        achou = False
        for m in padrao.finditer(base):
            trecho = texto[m.start():m.end()].strip()
            if trecho and trecho.lower() not in vistos:
                vistos.add(trecho.lower())
                trechos.append(trecho)
            achou = True
        if achou:  # cada gatilho conta uma vez, por mais que se repita na fala
            total += peso
    return total, trechos


def sugerir_caracteristicas(texto: str, catalogo: Any, limite: int = LIMITE_SUGESTOES) -> list[Sugestao]:
    """Sugere características do `catalogo` (CharacteristicCatalog) compatíveis com o relato `texto`."""
    if not texto or not texto.strip():
        return []
    base = normalizar(texto)
    achadas: list[tuple[int, int, Sugestao]] = []
    for ordem, item in enumerate(catalogo.caracteristicas):
        padroes = _COMPILADO.get(item.id_caracteristica)
        if padroes is None:  # característica nova no catálogo: reserva pelas palavras-chave dela
            padroes = [(_compilar(normalizar(k).strip()), PESO_FRACO) for k in item.palavras_chave_busca if k.strip()]
        pontos, trechos = _pontuar(texto, base, padroes)
        if pontos >= LIMIAR:
            achadas.append((-pontos, ordem, Sugestao(
                item.id_caracteristica, item.nome, pontos, "alta" if pontos >= 4 else "media", tuple(trechos[:4])
            )))
    achadas.sort(key=lambda t: (t[0], t[1]))
    return [s for _, _, s in achadas[:limite]]
