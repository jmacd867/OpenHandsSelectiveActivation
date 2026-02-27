"""
section_parser.py — Selective Context Activation

Splits an AGENTS.md file by Markdown headers (## and ###) into a list of
KnowledgeMicroagent instances, one per logical section. Each section gets
keyword triggers derived from its header tokens and high-frequency nouns in
the section body.

This module has zero dependency on the OpenHands agent loop. It only imports
from openhands.microagent, making it safe to unit-test in isolation.
"""

import re
from collections import Counter
from pathlib import Path


from openhands.microagent.types import MicroagentMetadata, MicroagentType

# ---------------------------------------------------------------------------
# Stop-words: tokens that should never become triggers on their own.
# Kept minimal — we want real nouns, not conjunctions or articles.
# ---------------------------------------------------------------------------
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "be", "been", "being", "was",
    "were", "has", "have", "had", "do", "does", "did", "will", "would",
    "should", "can", "could", "may", "might", "not", "no", "this", "that",
    "these", "those", "it", "its", "as", "if", "all", "any", "each",
    "before", "after", "when", "where", "how", "what", "which", "who",
    "than", "then", "so", "only", "also", "use", "run", "add", "make",
    "see", "per", "more", "new", "see", "via", "e.g", "i.e", "instructions",
    "tips", "guide", "overview", "details", "info", "notes", "you",
    "entire", "including", "fixed", "made", "issue", "issues"
}

_SYNONYMS: dict[str, list[str]] = {
    "pr":        ["pull request"],
    "commit":    ["git commit"],
    "test":      ["testing", "tests"],
    "tests":     ["testing", "test"],
    "gradlew":   ["gradle"],
    "sdk":       ["temporal sdk"],
    "api":       ["interface"],
}

# Minimum character length for a token to be considered a trigger candidate.
_MIN_TOKEN_LEN = 3

# Number of high-frequency body nouns to add as supplementary triggers.
_TOP_BODY_NOUNS = 3


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stripping punctuation."""
    return [t for t in re.findall(r"[a-z0-9](?:[a-z0-9\-\.]*[a-z0-9])?", text.lower())
            if len(t) >= _MIN_TOKEN_LEN and t not in _STOP_WORDS]


def _header_triggers(header: str) -> list[str]:
    """
    Extract trigger keywords directly from a section header.

    The header tokens are the highest-signal triggers because they name the
    section explicitly (e.g. 'Building and Testing' → ['building', 'testing']).
    Multi-word headers also produce a normalised phrase trigger.
    """
    # Strip leading # characters and whitespace
    clean = re.sub(r"^#+\s*", "", header).strip().rstrip(":")
    tokens = _tokenize(clean)

    triggers = list(tokens)  # individual word triggers

    # Also add the full normalised phrase as a trigger if it's multi-word
    phrase = clean.lower().strip()
    if phrase and phrase not in triggers:
        triggers.append(phrase)

    return triggers


def _body_triggers(body: str, header_triggers: list[str]) -> list[str]:
    """
    Extract high-frequency nouns from the section body as supplementary triggers.

    Avoids duplicating tokens already present in header_triggers.
    """
    tokens = _tokenize(body)
    existing = set(header_triggers)
    counts = Counter(t for t in tokens if t not in existing)
    return [word for word, _ in counts.most_common(_TOP_BODY_NOUNS)]

def _tfidf_triggers(
    sections: list[tuple[str, str]],
    top_n: int = 3,
) -> list[list[str]]:
    """
    For each section, return the top_n body tokens ranked by TF-IDF score
    across all sections.

    sections: list of (header_line, body) tuples
    Returns: list of trigger lists, one per section, in same order
    """
    # Tokenize all bodies
    tokenized = [_tokenize(body) for _, body in sections]

    # Document frequency: how many sections contain each token
    n_sections = len(tokenized)
    doc_freq: Counter = Counter()
    for tokens in tokenized:
        for tok in set(tokens):
            doc_freq[tok] += 1

    result = []
    for tokens in tokenized:
        if not tokens:
            result.append([])
            continue

        # Term frequency for this section
        tf = Counter(tokens)
        total = len(tokens)

        # TF-IDF score: (count/total) * (1 / doc_freq)
        # Higher score = appears often here, rarely elsewhere
        scores = {
            tok: (count / total) * (1.0 / doc_freq[tok])
            for tok, count in tf.items()
        }
        top = sorted(scores, key=lambda t: scores[t], reverse=True)[:top_n]
        result.append(top)

    return result


def parse_sections(
    content: str,
    source_path: str = "AGENTS.md",
    header_level: str = "##",
) -> list:
    from openhands.microagent.microagent import KnowledgeMicroagent

    if header_level not in ("##", "###"):
        raise ValueError(f"header_level must be '##' or '###', got: {header_level!r}")

    escaped = re.escape(header_level)
    pattern = re.compile(rf"^({escaped}(?!#)\s+.+)$", re.MULTILINE)
    matches = list(pattern.finditer(content))
    if not matches:
        return []

    # Pass 1: collect raw sections
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        header_line = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        sections.append((header_line, body))

    # Pass 2: score body triggers via TF-IDF across all sections
    tfidf_results = _tfidf_triggers(sections)

    agents: list[KnowledgeMicroagent] = []
    for (header_line, body), body_triggers in zip(sections, tfidf_results):
        h_triggers = _header_triggers(header_line)

        # Expand with synonyms
        expanded: list[str] = []
        for t in h_triggers + body_triggers:
            expanded.append(t)
            for syn in _SYNONYMS.get(t, []):
                if syn not in expanded:
                    expanded.append(syn)

        all_triggers = list(dict.fromkeys(expanded))
        if not all_triggers:
            print(f"[SCA] Warning: no triggers for section '{header_line}', skipping.")
            continue

        slug = re.sub(r"^#+\s*", "", header_line).strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        agent_name = f"sca_{slug}"

        metadata = MicroagentMetadata(
            name=agent_name,
            type=MicroagentType.KNOWLEDGE,
            triggers=all_triggers,
        )
        agent = KnowledgeMicroagent(
            name=agent_name,
            content=f"{header_line}\n{body}",
            metadata=metadata,
            source=source_path,
            type=MicroagentType.KNOWLEDGE,
        )
        agents.append(agent)

    return agents


# ---------------------------------------------------------------------------
# Quick smoke-test: run directly to validate against the two benchmark files.
# Usage:  python section_parser.py path/to/AGENTS.md
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("AGENTS.md")
    raw = path.read_text(encoding="utf-8")
    agents = parse_sections(raw, source_path=str(path))

    print(f"\nParsed {len(agents)} section(s) from {path.name}\n")
    for a in agents:
        print(f"  [{a.name}]")
        print(f"    triggers : {a.triggers}")
        print(f"    content  : {a.content[:80].replace(chr(10), ' ')!r}...")
        print()
