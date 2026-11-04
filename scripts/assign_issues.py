"""
Script para atribuir EXCLUSIVAMENTE as issues prioritárias da Semana 1/2
aos 5 integrantes do grupo no GitHub:
- matheushpr94 (Matheus Rosa - Integrante 1)
- iancostag (Ian Costa - Integrante 2)
- sarahgleice (Sarah Gleice - Integrante 3)
- Madu030 (Maria Eduarda - Integrante 4)
- ySamantha (Samantha Yumi - Integrante 5)
"""
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from scripts.sync_github_backlog import get_github_token, github_request, API_BASE

# Apenas as issues do Sprint 1 (Semanas 1 e 2 do Challenge 2)
SPRINT_ASSIGNEES = {
    # Integrante 3 (Back) + Integrante 5 (Front): Entrada de Material Didático
    4: ["sarahgleice", "ySamantha"],

    # Integrante 2 (Catálogo/Dados) + Integrante 5 (Front): Seleção Cirúrgica de Características
    8: ["iancostag", "ySamantha"],

    # Integrante 1 (RAG & Ingestão): Base Científica RAG e EDA 1
    16: ["matheushpr94"],

    # Integrante 3 (Backend & LGPD): Scrubber Preventivo de PII (Zero-Retention)
    34: ["sarahgleice"],

    # Integrante 2 (Pedagogia & Catálogo): Catálogo Oficial de Características TDAH (JSON)
    39: ["iancostag"],

    # Integrante 4 (Métricas & Avaliação) + Integrante 1 (RAG): EDA Benchmark e RAGAS
    40: ["Madu030", "matheushpr94"],
}


def main():
    token = get_github_token()
    print("=== Atribuindo Apenas as Issues do Sprint 1 (Semana 1 e 2) ===")

    for issue_num, assignees in SPRINT_ASSIGNEES.items():
        try:
            res = github_request(
                "POST",
                f"{API_BASE}/issues/{issue_num}/assignees",
                token,
                {"assignees": assignees},
            )
            current = [u["login"] for u in res.get("assignees", [])]
            print(f"  [ATRIBUÍDA #{issue_num:02d}] -> {', '.join(current)}")
            time.sleep(0.3)
        except Exception as e:
            print(f"  [ERRO #{issue_num:02d}]: {e}")

    print("\nConcluído! Apenas as issues da semana foram atribuídas.")


if __name__ == "__main__":
    main()
