"""
tests/unit/test_section_parser.py

Integration tests for the SCA section parser against the two benchmark
AGENTS.md files collected for the project.
"""

import pytest
from pathlib import Path
from openhands.microagent.section_parser import parse_sections

# Paths to the two benchmark files
TEMPORAL_AGENTS_MD = Path("agents2.md")   # Temporal Java SDK
REACT_AGENTS_MD = Path("agents1.md")      # React/TS monorepo


@pytest.fixture
def temporal_content():
    return TEMPORAL_AGENTS_MD.read_text(encoding="utf-8")


@pytest.fixture
def react_content():
    return REACT_AGENTS_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Section count tests — most critical, silent failure if wrong
# ---------------------------------------------------------------------------

def test_temporal_section_count(temporal_content):
    agents = parse_sections(temporal_content)
    assert len(agents) == 6, (
        f"Expected 6 sections from Temporal AGENTS.md, got {len(agents)}: "
        f"{[a.name for a in agents]}"
    )


def test_react_section_count(react_content):
    agents = parse_sections(react_content)
    assert len(agents) == 3, (
        f"Expected 3 sections from React AGENTS.md, got {len(agents)}: "
        f"{[a.name for a in agents]}"
    )


# ---------------------------------------------------------------------------
# Agent name tests
# ---------------------------------------------------------------------------

def test_temporal_agent_names(temporal_content):
    agents = parse_sections(temporal_content)
    names = [a.name for a in agents]
    assert "sca_repository_layout" in names
    assert "sca_general_guidance" in names
    assert "sca_building_and_testing" in names
    assert "sca_tests" in names
    assert "sca_commit_messages_and_pull_requests" in names
    assert "sca_review_checklist" in names


def test_react_agent_names(react_content):
    agents = parse_sections(react_content)
    names = [a.name for a in agents]
    assert "sca_dev_environment_tips" in names
    assert "sca_testing_instructions" in names
    assert "sca_pr_instructions" in names


# ---------------------------------------------------------------------------
# Trigger quality tests
# ---------------------------------------------------------------------------

def test_building_and_testing_has_gradlew(temporal_content):
    agents = parse_sections(temporal_content)
    agent = next(a for a in agents if a.name == "sca_building_and_testing")
    assert "gradlew" in agent.triggers, (
        f"Expected 'gradlew' in sca_building_and_testing triggers, got: {agent.triggers}"
    )


def test_commit_section_has_commit_trigger(temporal_content):
    agents = parse_sections(temporal_content)
    agent = next(a for a in agents if a.name == "sca_commit_messages_and_pull_requests")
    assert "commit" in agent.triggers


def test_pr_section_has_pr_trigger(react_content):
    agents = parse_sections(react_content)
    agent = next(a for a in agents if a.name == "sca_pr_instructions")
    assert "pr instructions" in agent.triggers


# ---------------------------------------------------------------------------
# Duplicate trigger tests
# ---------------------------------------------------------------------------

def test_no_duplicate_triggers_temporal(temporal_content):
    agents = parse_sections(temporal_content)
    for agent in agents:
        triggers = agent.triggers
        assert len(triggers) == len(set(triggers)), (
            f"Duplicate triggers in {agent.name}: {triggers}"
        )


def test_no_duplicate_triggers_react(react_content):
    agents = parse_sections(react_content)
    for agent in agents:
        triggers = agent.triggers
        assert len(triggers) == len(set(triggers)), (
            f"Duplicate triggers in {agent.name}: {triggers}"
        )


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

def test_empty_content_returns_no_agents():
    agents = parse_sections("")
    assert agents == []


def test_content_with_no_headers_returns_no_agents():
    agents = parse_sections("just some text with no markdown headers")
    assert agents == []


def test_invalid_header_level_raises():
    with pytest.raises(ValueError):
        parse_sections("## Section", header_level="####")


# ---------------------------------------------------------------------------
# match_trigger end-to-end tests — validates activation behaviour
# ---------------------------------------------------------------------------

def test_match_trigger_gradlew_message(temporal_content):
    agents = parse_sections(temporal_content)
    agent = next(a for a in agents if a.name == "sca_building_and_testing")
    result = agent.match_trigger("I need to run gradlew to build the project")
    assert result is not None, (
        f"sca_building_and_testing should activate on 'gradlew' message, triggers: {agent.triggers}"
    )


def test_match_trigger_commit_message(temporal_content):
    agents = parse_sections(temporal_content)
    agent = next(a for a in agents if a.name == "sca_commit_messages_and_pull_requests")
    result = agent.match_trigger("I am ready to commit these changes")
    assert result is not None


def test_match_trigger_pr_react(react_content):
    agents = parse_sections(react_content)
    agent = next(a for a in agents if a.name == "sca_pr_instructions")
    result = agent.match_trigger("What is the correct PR title format for this project?")
    assert result is not None


def test_match_trigger_no_false_positive(temporal_content):
    """Review checklist should not fire on a generic code-writing message."""
    agents = parse_sections(temporal_content)
    agent = next(a for a in agents if a.name == "sca_review_checklist")
    result = agent.match_trigger("I will write a new function for the API")
    assert result is None, (
        f"sca_review_checklist fired unexpectedly. Matched: {result}. "
        f"Triggers: {agent.triggers}"
    )


# ---------------------------------------------------------------------------
# Over-suppression rate tests — recall check: no section is permanently dark
# ---------------------------------------------------------------------------

_TEMPORAL_ACTIVATION_MESSAGES = {
    "sca_repository_layout":                  "Where is the temporal-sdk module located in the repository?",
    "sca_general_guidance":                   "Should I avoid changing public API signatures here?",
    "sca_building_and_testing":               "I need to run gradlew to execute the test suite.",
    "sca_tests":                              "Where are the tests located for the temporal-sdk package?",
    "sca_commit_messages_and_pull_requests":  "I am writing a commit message for these changes.",
    "sca_review_checklist":                   "I need to run spotlesscheck before merging.",
}

_REACT_ACTIVATION_MESSAGES = {
    "sca_dev_environment_tips":   "How do I set up the vite dev environment for this package?",
    "sca_testing_instructions":   "I need to run the test suite with pnpm turbo.",
    "sca_pr_instructions":        "What is the correct PR title format for this project?",
}


def test_no_section_permanently_dark_temporal(temporal_content):
    """Every Temporal section must activate on at least one realistic message."""
    agents = parse_sections(temporal_content)
    for agent in agents:
        message = _TEMPORAL_ACTIVATION_MESSAGES.get(agent.name)
        assert message is not None, f"No activation message defined for {agent.name}"
        result = agent.match_trigger(message)
        assert result is not None, (
            f"Section '{agent.name}' failed to activate.\n"
            f"  Message : {message}\n"
            f"  Triggers: {agent.triggers}"
        )


def test_no_section_permanently_dark_react(react_content):
    """Every React section must activate on at least one realistic message."""
    agents = parse_sections(react_content)
    for agent in agents:
        message = _REACT_ACTIVATION_MESSAGES.get(agent.name)
        assert message is not None, f"No activation message defined for {agent.name}"
        result = agent.match_trigger(message)
        assert result is not None, (
            f"Section '{agent.name}' failed to activate.\n"
            f"  Message : {message}\n"
            f"  Triggers: {agent.triggers}"
        )

def test_content_includes_header(temporal_content):
    agents = parse_sections(temporal_content)
    agent = next(a for a in agents if a.name == "sca_building_and_testing")
    assert agent.content.startswith("## Building and Testing"), (
        f"Expected content to start with header line, got: {agent.content[:80]}"
    )
