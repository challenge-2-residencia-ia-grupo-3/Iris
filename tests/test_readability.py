from iris.eval.readability import (
    analyze_question,
    count_conjugated_commands,
    count_syllables,
    find_commands,
    flesch_ptbr,
    split_sentences,
)


def test_syllables():
    assert count_syllables("casa") == 2
    assert count_syllables("aluno") == 3
    assert count_syllables("o") == 1


def test_sentences():
    assert len(split_sentences("Leia o texto. Responda! Por quê?")) == 3


def test_flesch_simple_text_is_easier_than_complex():
    simple = "O gato bebe leite. O cão corre no parque."
    complex_ = (
        "A fotossintetização constitui um processo bioquímico extremamente "
        "complexo, desencadeado pela absorção de radiação eletromagnética."
    )
    assert flesch_ptbr(simple) > flesch_ptbr(complex_)


def test_flesch_empty():
    assert flesch_ptbr("") is None


def test_commands_with_accents_and_case():
    assert find_commands("Leia o texto e Justifique sua resposta.") == ["leia", "justifique"]


def test_conjugated_commands():
    assert count_conjugated_commands("Leia o texto e responda.") == 2
    assert count_conjugated_commands("Leia o texto. Responda.") == 0
    assert count_conjugated_commands("Analise, compare e justifique.") == 3


def test_analyze_question():
    s = analyze_question("Q01", "Leia o texto e responda. Justifique.")
    assert s.n_commands == 3
    assert s.n_conjugated_commands == 2
    assert s.has_conjugated_command

def test_commands_with_clitic():
    assert find_commands("Classifique-o e escreva-a em seguida.") == ["classifique", "escreva"]
