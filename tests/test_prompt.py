from app.prompt import DISCLAIMER, SYSTEM_PROMPT


def test_system_prompt_is_clinical_support_without_specialty():
    assert SYSTEM_PROMPT.strip()
    lowered = SYSTEM_PROMPT.lower()
    assert "диагноз" in lowered
    assert "суждение" in lowered
    assert "перинат" not in lowered
    assert "неонат" not in lowered


def test_disclaimer_present():
    assert DISCLAIMER.strip()
    lowered = DISCLAIMER.lower()
    assert "диагноз" in lowered
    assert "врач" in lowered
