"""Unit tests for prompts.py.

Prompts are configuration, not code, so the tests here guard two things a
type checker cannot:

1. The templates format without KeyError, and only on the placeholders they
   are supposed to have. A KeyError in ``synthesis_node`` surfaces to the user
   as a generic failure message, which is the worst possible way to discover a
   typo in a brace.
2. The load-bearing Turkish strings are present verbatim. The compliance
   posture of the whole product rests on the model reproducing them exactly,
   so a silent edit here is a regulatory change disguised as a copy edit.
"""

from __future__ import annotations

import pytest

import prompts

def flat(text: str) -> str:
    """Collapse newlines so assertions survive line wrapping.

    The prompts are hard-wrapped at 78 columns, so a phrase like
    "not user-facing" is frequently split across two lines. Asserting on the
    raw string would make every reflow a test failure, which trains people to
    weaken the assertions.
    """
    return " ".join(text.split())


SPECIALIST_KEYS = {
    "PORTFOLIO_AGENT",
    "MARKET_RESEARCH_AGENT",
    "RISK_STRATEGY_AGENT",
    "TRANSACTION_AGENT",
    "COMPLIANCE_AGENT",
}


# --------------------------------------------------------------------------
# Template formatting
# --------------------------------------------------------------------------
def test_synthesis_template_formats_with_exactly_its_placeholders():
    rendered = prompts.SYNTHESIS_TASK_TEMPLATE.format(
        user_message="portföyüm ne durumda?",
        primary_intent="PORTFOLIO_INQUIRY",
        target_agent="PORTFOLIO_AGENT",
        specialist_json='{"status": "OK"}',
    )
    assert "portföyüm ne durumda?" in rendered
    assert "PORTFOLIO_AGENT" in rendered
    assert "{" not in rendered.replace('{"status": "OK"}', "")


def test_synthesis_template_raises_on_a_missing_placeholder():
    """Pins the failure mode so a renamed state key cannot pass silently."""
    with pytest.raises(KeyError):
        prompts.SYNTHESIS_TASK_TEMPLATE.format(user_message="x")


def test_revision_template_formats_with_exactly_its_placeholders():
    rendered = prompts.REVISION_TASK_TEMPLATE.format(
        previous_draft="önceki taslak", blocked_reason="tavsiye içeriyor"
    )
    assert "önceki taslak" in rendered
    assert "tavsiye içeriyor" in rendered


def test_revision_template_raises_on_a_missing_placeholder():
    with pytest.raises(KeyError):
        prompts.REVISION_TASK_TEMPLATE.format(previous_draft="x")


def test_templates_accept_json_payloads_containing_braces():
    """The specialist envelope is JSON, so it is full of braces. They must
    survive as data rather than being read as format fields."""
    payload = '{"data": {"positions": [{"symbol": "THYAO"}]}}'
    rendered = prompts.SYNTHESIS_TASK_TEMPLATE.format(
        user_message="m", primary_intent="i", target_agent="a", specialist_json=payload
    )
    assert payload in rendered


def test_templates_accept_empty_strings():
    """Edge case: an empty specialist payload is legitimate for smalltalk."""
    rendered = prompts.SYNTHESIS_TASK_TEMPLATE.format(
        user_message="", primary_intent="", target_agent="", specialist_json=""
    )
    assert rendered.strip()


def test_system_prompts_must_never_be_passed_through_format():
    """Guard, not a wish.

    The specialist prompts embed literal JSON schemas, so calling .format on
    one raises. This test documents that hazard, because the natural refactor
    of 'let me interpolate the user id into the system prompt' would break the
    whole backend at runtime.
    """
    with pytest.raises((KeyError, IndexError, ValueError)):
        prompts.SPECIALIST_PROMPTS["PORTFOLIO_AGENT"].format(user_id="u_1")


def test_orchestrator_prompt_is_format_safe_by_accident_only():
    """It happens to contain no braces today. Asserting it keeps the fact
    true, since synthesis_node passes it as a system message unformatted."""
    assert "{" not in prompts.ORCHESTRATOR_SYSTEM_PROMPT
    assert "}" not in prompts.ORCHESTRATOR_SYSTEM_PROMPT


# --------------------------------------------------------------------------
# Load-bearing verbatim strings
# --------------------------------------------------------------------------
def test_mandatory_disclaimer_is_exact():
    """This sentence is quoted in the compliance rule pack. Changing so much
    as a comma is a regulatory change, not a copy edit."""
    assert (
        prompts.MANDATORY_DISCLAIMER
        == "Yatırım tavsiyesi olarak değil, objektif kriterlerle taradım."
    )


def test_headers_are_exact_and_bold():
    assert prompts.FILTERS_HEADER == "**Kullandığım filtreler:**"
    assert prompts.OBSERVATIONS_HEADER == "**Öne çıkan gözlemler:**"


@pytest.mark.parametrize(
    "constant",
    ["MANDATORY_DISCLAIMER", "FILTERS_HEADER", "OBSERVATIONS_HEADER"],
)
def test_verbatim_constants_appear_inside_the_orchestrator_prompt(constant):
    """The constants exist for code; the prompt must carry the same strings,
    or the model and the validator disagree about what verbatim means."""
    assert getattr(prompts, constant) in flat(prompts.ORCHESTRATOR_SYSTEM_PROMPT)


def test_turkish_orthography_is_not_ascii_substituted():
    """A prompt written with ASCII would teach the model to reply that way."""
    for char in "ıİşğüöç":
        assert char in prompts.ORCHESTRATOR_SYSTEM_PROMPT


def test_expectation_management_rejection_is_present():
    assert "**Kimse size kazandırır diyemez.**" in flat(prompts.ORCHESTRATOR_SYSTEM_PROMPT)


def test_five_onboarding_steps_are_present_in_order():
    prompt = prompts.ORCHESTRATOR_SYSTEM_PROMPT
    prompt = flat(prompt)
    steps = ["Acil durum fonu", "Risk profili", "Küçük başla", "Öğren", "Uzun vadeli düşün"]
    positions = [prompt.find(s) for s in steps]
    assert all(p > 0 for p in positions), dict(zip(steps, positions))
    assert positions == sorted(positions), "the five steps must stay in order"


@pytest.mark.parametrize(
    "rule",
    [
        "Never tell the user to buy, sell, hold",
        "You never execute",
        "is NOT confirmation",
        "Reply ENTIRELY IN TURKISH",
        "An empty result is a VALID, COMPLETE answer",
    ],
)
def test_hard_rules_survive_in_the_operative_subset(rule):
    """prompts.py carries a tightened version of the reviewed document. These
    are the clauses that may not be lost to tightening."""
    assert rule in flat(prompts.ORCHESTRATOR_SYSTEM_PROMPT)


def test_default_table_columns_are_specified():
    assert "1.000 TL ile lot" in prompts.ORCHESTRATOR_SYSTEM_PROMPT
    assert "| Hisse | Sektör |" in prompts.ORCHESTRATOR_SYSTEM_PROMPT


# --------------------------------------------------------------------------
# Specialist prompts
# --------------------------------------------------------------------------
def test_all_five_specialists_are_defined():
    assert set(prompts.SPECIALIST_PROMPTS) == SPECIALIST_KEYS


@pytest.mark.parametrize("agent", sorted(SPECIALIST_KEYS))
def test_every_specialist_declares_it_is_not_user_facing(agent):
    assert "not user-facing" in flat(prompts.SPECIALIST_PROMPTS[agent]).lower()


@pytest.mark.parametrize("agent", sorted(SPECIALIST_KEYS))
def test_every_specialist_is_english_only(agent):
    """A specialist that emits Turkish would leak backend text straight into
    the user-facing reply, since synthesis passes its output through."""
    text = flat(prompts.SPECIALIST_PROMPTS[agent])
    assert "English only" in text or "never emit Turkish" in text


@pytest.mark.parametrize(
    "agent,tool",
    [
        ("PORTFOLIO_AGENT", "get_portfolio_positions"),
        ("MARKET_RESEARCH_AGENT", "rag_semantic_market_search"),
        ("RISK_STRATEGY_AGENT", "calculate_portfolio_risk_metrics"),
        ("TRANSACTION_AGENT", "prepare_transaction_proposal"),
    ],
)
def test_tool_binding_names_exactly_one_tool(agent, tool):
    assert f"TOOL BINDING: {tool} only" in prompts.SPECIALIST_PROMPTS[agent]


@pytest.mark.parametrize(
    "agent",
    ["PORTFOLIO_AGENT", "MARKET_RESEARCH_AGENT", "RISK_STRATEGY_AGENT", "TRANSACTION_AGENT"],
)
def test_tool_using_specialists_carry_the_json_envelope_rule(agent):
    """The nodes parse the reply as JSON, so the instruction has to be there."""
    text = flat(prompts.SPECIALIST_PROMPTS[agent])
    assert "Emit exactly ONE JSON object and nothing else" in text
    assert "no code fences" in text


def test_compliance_agent_has_no_envelope_rule_because_it_calls_no_tool():
    """It relays a verdict rather than planning a call, so it is the one
    specialist without the JSON envelope. Pinned so nobody 'fixes' it."""
    text = flat(prompts.SPECIALIST_PROMPTS["COMPLIANCE_AGENT"])
    assert "Emit exactly ONE JSON object" not in text
    assert "FAIL CLOSED" in text


def test_transaction_specialist_forbids_fabrication_and_execution():
    text = flat(prompts.SPECIALIST_PROMPTS["TRANSACTION_AGENT"])
    assert "NEVER fabricate an IBAN" in text
    assert "Conversational assent is NOT confirmation" in text
    assert "never report anything as executed" in text.lower()


def test_market_research_specialist_marks_snippets_untrusted():
    text = flat(prompts.SPECIALIST_PROMPTS["MARKET_RESEARCH_AGENT"])
    assert "UNTRUSTED data" in text
    assert "never a" in text and "directive" in text


def test_specialist_prompts_are_short_enough_to_be_cheap():
    """These ship on every specialist call. A prompt that grows past a few
    thousand characters is a per-request cost regression."""
    for agent, text in prompts.SPECIALIST_PROMPTS.items():
        assert len(text) < 2500, f"{agent} is {len(text)} chars"


def test_no_prompt_is_empty_or_whitespace():
    everything = [prompts.ORCHESTRATOR_SYSTEM_PROMPT, *prompts.SPECIALIST_PROMPTS.values()]
    for text in everything:
        assert text.strip()
