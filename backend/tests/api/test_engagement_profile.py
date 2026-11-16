"""Testes unitários, de API e de não-substituição curricular da História 1.2.2 (Issue #9).

Verifica todos os Critérios de Aceitação BDD e Tarefas INVEST:
1. [Backend] Schema Pydantic (`extra='forbid'`) para potencialidades, interesses e canais preferenciais (Princípio I DUA).
2. [Backend / LGPD] Sanitização irreversível de PII em `potencialidades` e bloqueio de referências clínicas (CID, laudo, medicação).
3. [Backend / API] Integração opcional no endpoint/serviço da Etapa 2 sem quebrar a obrigatoriedade da seleção cirúrgica (1.2.1).
4. [RAG / IA] Mapeamento dos metadados de engajamento para injeção motivacional no prompt de adaptação.
5. [Testes / TRCC] Comprovação determinística de que a injeção de potencialidades e interesses não substitui
   os conceitos obrigatórios exigidos pela Trava Curricular (TRCC >= 95%).
6. [Frontend] Contrato de UI da Etapa 2 (seletores de interesses `esportes`, `natureza`, `tecnologia`,
   campo de potencialidades, acessibilidade e persistência em `sessionStorage`).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris.api.routes.catalogs import (
    get_engagement_options_service,
    register_engagement_profile_service,
    select_surgical_characteristics_service,
)
from iris.rag.engagement_context import (
    build_motivational_context,
    inject_motivational_context_into_prompt,
    verify_motivational_adaptation_preserves_curriculum,
)
from iris.schemas.engagement import (
    DUA_PRINCIPLE_ID,
    EngagementProfileInput,
    EngagementValidationError,
    validate_engagement_profile,
)


class TestEngagementSchemaAndPrivacy(unittest.TestCase):
    """Validação do schema Pydantic, opcionalidade, anti-clínica e sanitização PII (História 1.2.2)."""

    def test_engagement_options_service_returns_dua_principle_1_catalog(self) -> None:
        options = get_engagement_options_service()
        self.assertEqual(options["principio_dua"], DUA_PRINCIPLE_ID)
        self.assertFalse(options["obrigatorio"])
        self.assertFalse(options["exige_laudo_medico"])
        interest_ids = {item["id"] for item in options["interesses_tematicos"]}
        self.assertTrue({"esportes", "natureza", "tecnologia"}.issubset(interest_ids))
        channel_ids = {item["id"] for item in options["canais_engajamento_preferenciais"]}
        self.assertIn("esquemas_visuais", channel_ids)

    def test_empty_engagement_profile_is_valid_and_optional(self) -> None:
        model = EngagementProfileInput()
        self.assertEqual(model.interesses_tematicos, [])
        meta = validate_engagement_profile({})
        self.assertEqual(meta.principio_dua, DUA_PRINCIPLE_ID)
        self.assertFalse(meta.possui_ancoras_motivacionais)
        self.assertIsNone(meta.potencialidades)

    def test_extra_forbid_rejects_clinical_or_undeclared_fields(self) -> None:
        with self.assertRaises(EngagementValidationError) as ctx:
            validate_engagement_profile(
                {
                    "interesses_tematicos": ["esportes"],
                    "cid_medico": "F90.0",
                }
            )
        self.assertEqual(ctx.exception.code, "CLINICAL_OR_EXTRA_FIELD_FORBIDDEN")
        self.assertEqual(ctx.exception.field, "cid_medico")

    def test_rejects_clinical_terms_inside_potencialidades_free_text(self) -> None:
        with self.assertRaises(EngagementValidationError) as ctx:
            validate_engagement_profile(
                {
                    "potencialidades": "Possui laudo médico CID F90.0 e usa ritalina antes da prova.",
                }
            )
        self.assertEqual(ctx.exception.code, "CLINICAL_CONTENT_FORBIDDEN")
        self.assertEqual(ctx.exception.field, "potencialidades")

    def test_sanitizes_accidental_pii_in_potencialidades_zero_retention(self) -> None:
        meta = validate_engagement_profile(
            {
                "interesses_tematicos": ["natureza"],
                "potencialidades": (
                    "O aluno Gabriel Silva tem facilidade com esquemas visuais. "
                    "Contato: marina@escola.edu.br"
                ),
            }
        )
        self.assertTrue(meta.sanitized)
        self.assertGreaterEqual(meta.pii_removed_count, 2)
        self.assertIsNotNone(meta.potencialidades)
        assert meta.potencialidades is not None
        self.assertNotIn("Gabriel Silva", meta.potencialidades)
        self.assertNotIn("marina@escola.edu.br", meta.potencialidades)
        self.assertIn("[ESTUDANTE]", meta.potencialidades)
        self.assertIn("[EMAIL]", meta.potencialidades)
        self.assertIn("facilidade com esquemas visuais", meta.potencialidades)


class TestEngagementIntegrationAndPromptInjection(unittest.TestCase):
    """Validação da integração com Etapa 2, mapeamento RAG/IA e não-substituição da Trava Curricular."""

    def test_select_characteristics_attaches_dua_engagement_metadata(self) -> None:
        result = select_surgical_characteristics_service(
            {
                "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                "engagement_profile": {
                    "interesses_tematicos": ["esportes", "tecnologia"],
                    "interesses_customizados": ["astronomia"],
                    "canais_engajamento_preferenciais": ["esquemas_visuais"],
                    "potencialidades": "Facilidade com esquemas visuais e raciocínio lógico.",
                },
            }
        )
        dumped = result.model_dump()
        self.assertEqual(dumped["selected_count"], 1)
        self.assertIn("engagement_metadata", dumped)
        self.assertIn("motivational_context", dumped)

        eng = dumped["engagement_metadata"]
        self.assertEqual(eng["principio_dua"], DUA_PRINCIPLE_ID)
        self.assertTrue(eng["possui_ancoras_motivacionais"])
        self.assertEqual(
            [i["id"] for i in eng["interesses_tematicos"]],
            ["esportes", "tecnologia"],
        )
        self.assertEqual(eng["interesses_customizados"], ["astronomia"])

        mot = dumped["motivational_context"]
        self.assertIn("Princípio I do DUA", mot["prompt_section"])
        self.assertIn("Esportes e Movimento", mot["prompt_section"])
        self.assertIn("Esquemas Visuais e Mapas", mot["prompt_section"])

    def test_register_engagement_profile_with_rag_evidence_lookup(self) -> None:
        resp = register_engagement_profile_service(
            payload={
                "interesses_tematicos": ["natureza"],
                "canais_engajamento_preferenciais": ["exemplos_concretos"],
                "potencialidades": "Compreende melhor quando vê exemplos concretos antes da teoria.",
            },
            travas_curriculares=["fotossíntese", "clorofila", "energia luminosa"],
            fetch_rag_evidence=True,
        )
        self.assertEqual(resp["status"], "success")
        mot = resp["motivational_context"]
        self.assertEqual(
            mot["conceitos_trava_protegidos"],
            ["fotossíntese", "clorofila", "energia luminosa"],
        )
        self.assertIn("fotossíntese, clorofila, energia luminosa", mot["prompt_section"])
        self.assertIsInstance(mot["evidencias_rag"], list)

    def test_inject_motivational_context_into_prompt_is_noop_when_empty(self) -> None:
        base_prompt = "Adapte o enunciado apenas dividindo comandos múltiplos."
        empty_meta = validate_engagement_profile({})
        injected = inject_motivational_context_into_prompt(
            base_prompt=base_prompt,
            engagement=empty_meta,
            travas_curriculares=["equação do 1º grau"],
        )
        self.assertEqual(injected, base_prompt)

    def test_motivational_injection_does_not_substitute_curriculum_lock_concepts(self) -> None:
        """Garante via prompt e TRCC determinístico que interesses não substituem a Trava Curricular."""
        travas = ["fotossíntese", "clorofila", "energia luminosa", "glicose"]
        engagement = validate_engagement_profile(
            {
                "interesses_tematicos": ["esportes", "natureza"],
                "canais_engajamento_preferenciais": ["esquemas_visuais"],
                "potencialidades": "Facilidade com esquemas visuais.",
            }
        )

        # 1. O bloco injetado no prompt protege explicitamente os conceitos da trava
        ctx = build_motivational_context(engagement=engagement, travas_curriculares=travas)
        prompt_final = inject_motivational_context_into_prompt(
            base_prompt="Reestruture a questão mantendo 100% da habilidade avaliada.",
            engagement=engagement,
            travas_curriculares=travas,
        )
        self.assertTrue(ctx.possui_ancoras_motivacionais)
        self.assertIn("REGRAS INEGOCIÁVEIS DE PRESERVAÇÃO CURRICULAR (ANTI-SUBSTITUIÇÃO)", prompt_final)
        for conceito in travas:
            self.assertIn(conceito, prompt_final)

        # 2. Adaptação válida usa âncora motivacional (esporte + esquema visual) e preserva todos os conceitos
        adaptacao_conforme = (
            "Organize em um esquema visual como um atleta usa energia durante uma partida. "
            "Da mesma forma que o corpo precisa de combustível, a planta realiza a fotossíntese: "
            "[ ] Identifique o papel da clorofila na captação da energia luminosa. "
            "[ ] Explique como esse processo resulta na produção de glicose."
        )
        check_ok = verify_motivational_adaptation_preserves_curriculum(adaptacao_conforme, travas)
        self.assertTrue(check_ok["preservou_trava"])
        self.assertEqual(check_ok["trcc"], 1.0)
        self.assertEqual(check_ok["status"], "aprovado")

        # 3. Controle negativo: se a adaptação substituir os conceitos de biologia por termos de futebol, é barrada
        adaptacao_substituida = (
            "Organize em um esquema visual como um jogador de futebol ganha fôlego no campo "
            "para correr mais rápido durante o segundo tempo da partida."
        )
        check_fail = verify_motivational_adaptation_preserves_curriculum(adaptacao_substituida, travas)
        self.assertFalse(check_fail["preservou_trava"])
        self.assertLess(check_fail["trcc"], 0.95)
        self.assertEqual(check_fail["status"], "violacao_substituicao_curricular")
        self.assertEqual(set(check_fail["conceitos_ausentes"]), set(travas))


class TestFrontendEngagementContract(unittest.TestCase):
    """Verifica contrato de UI da Etapa 2 para potencialidades, interesses temáticos e sessão."""

    def test_frontend_step2_exposes_engagement_selectors_and_session_persistence(self) -> None:
        step2_path = REPO_ROOT / "frontend" / "src" / "components" / "Step2FunctionalProfile.tsx"
        api_path = REPO_ROOT / "frontend" / "src" / "services" / "catalogsApi.ts"

        step2_code = step2_path.read_text(encoding="utf-8")
        api_code = api_path.read_text(encoding="utf-8")

        # Interesses temáticos obrigatórios da especificação (esportes, natureza, tecnologia)
        for interest_id in ("esportes", "natureza", "tecnologia"):
            self.assertIn(f'"{interest_id}"', api_code)

        # Campo de potencialidades, canais preferenciais e vínculo ao Princípio I do DUA
        self.assertIn("Potencialidades, Interesses e Canais de Engajamento", step2_code)
        self.assertIn("Princípio I do DUA", step2_code)
        self.assertIn("potencialidades", step2_code)
        self.assertIn("canais_engajamento_preferenciais", step2_code)
        self.assertIn("aria-pressed={isActive}", step2_code)

        # Consumo de endpoint e persistência em sessionStorage
        self.assertIn("/api/v1/catalogs/engagement-options", api_code)
        self.assertIn("ENGAGEMENT_PROFILE_STORAGE_KEY", api_code)
        self.assertIn("saveEngagementProfileToSession", step2_code)
        self.assertIn("loadEngagementProfileFromSession", step2_code)


try:
    from fastapi.testclient import TestClient
    from iris.main import create_app

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


@unittest.skipUnless(HAS_FASTAPI, "FastAPI/TestClient não disponível no Python atual")
class TestEngagementFastAPIRoutes(unittest.TestCase):
    """Testes HTTP dos endpoints FastAPI da História 1.2.2."""

    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_engagement_options_endpoint(self) -> None:
        resp = self.client.get("/api/v1/catalogs/engagement-options")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["principio_dua"], DUA_PRINCIPLE_ID)
        self.assertFalse(data["obrigatorio"])

    def test_post_engagement_endpoint_sanitizes_and_rejects_clinical_fields(self) -> None:
        ok_resp = self.client.post(
            "/api/v1/catalogs/engagement",
            json={
                "interesses_tematicos": ["esportes", "tecnologia"],
                "canais_engajamento_preferenciais": ["esquemas_visuais"],
                "potencialidades": "O aluno Pedro Costa compreende bem esquemas visuais.",
            },
        )
        self.assertEqual(ok_resp.status_code, 200)
        body = ok_resp.json()
        self.assertTrue(body["engagement_metadata"]["sanitized"])
        self.assertNotIn("Pedro Costa", body["engagement_metadata"]["potencialidades"])

        bad_resp = self.client.post(
            "/api/v1/catalogs/engagement",
            json={"interesses_tematicos": ["esportes"], "laudo_medico": "F90.0"},
        )
        self.assertEqual(bad_resp.status_code, 422)
        self.assertEqual(bad_resp.json()["detail"]["code"], "CLINICAL_OR_EXTRA_FIELD_FORBIDDEN")

    def test_select_characteristics_endpoint_with_engagement_profile(self) -> None:
        resp = self.client.post(
            "/api/v1/catalogs/characteristics/select",
            json={
                "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                "engagement_profile": {
                    "interesses_tematicos": ["natureza"],
                    "canais_engajamento_preferenciais": ["exemplos_concretos"],
                    "potencialidades": "Facilidade com observação prática.",
                },
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["selected_count"], 1)
        self.assertEqual(data["engagement_metadata"]["principio_dua"], DUA_PRINCIPLE_ID)
        self.assertIn("Natureza e Meio Ambiente", data["motivational_context"]["prompt_section"])


if __name__ == "__main__":
    unittest.main()
