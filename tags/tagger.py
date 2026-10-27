"""Rule-based provision tagger.

Beta approach: transparent regex rules per tag, reviewed like code. The same
interface can later be backed by an LLM classifier that proposes tags for
human review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from laws.domain.units import ActText

DEFAULT_RULES = Path(__file__).parent / "rules" / "pl_driving.yaml"


@dataclass
class TagRules:
    tags: dict[str, dict[str, str]]  # slug -> {"pl": ..., "en": ...}
    patterns: dict[str, list[re.Pattern]]
    act_tags: dict[str, list[str]]
    questionnaire: dict[str, dict] = field(default_factory=dict)  # key -> {"label": ..., "tags": [...]}

    @classmethod
    def load(cls, path: Path | None = None) -> TagRules:
        raw = Path(path or DEFAULT_RULES).read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        tags = data.get("tags", {})
        rules = data.get("rules", {})
        questionnaire = data.get("questionnaire", {})
        referenced = [
            *rules,
            *(t for ts in data.get("acts", {}).values() for t in ts),
            *(t for q in questionnaire.values() for t in q["tags"]),
        ]
        for slug in referenced:
            if slug not in tags:
                raise ValueError(f"rule refers to undefined tag {slug!r}")
        return cls(
            tags=tags,
            patterns={slug: [re.compile(p, re.I) for p in pats] for slug, pats in rules.items()},
            act_tags=data.get("acts", {}),
            questionnaire=questionnaire,
        )

    def tag(self, text: ActText) -> dict[str, set[str]]:
        """Return {address: {tag slugs}} for units that match directly.

        Inherited tags are not repeated on descendants; consumers resolve
        inheritance by walking up the address tree.
        """
        result: dict[str, set[str]] = {}
        act_key = f"{text.act.jurisdiction}:{text.act.source_id}"
        if self.act_tags.get(act_key):
            result[""] = set(self.act_tags[act_key])
        for unit, _ in text.root.walk():
            if unit.kind == "act":
                continue
            haystack = " ".join(filter(None, [unit.heading, unit.text, unit.tail]))
            hits = {slug for slug, pats in self.patterns.items() if any(p.search(haystack) for p in pats)}
            if hits:
                result.setdefault(unit.address, set()).update(hits)
        return result

    def suggest(self, answers: dict[str, bool]) -> list[str]:
        """Tags to pre-select for a user from their questionnaire answers."""
        out: list[str] = []
        for question, yes in answers.items():
            if yes:
                out.extend(t for t in self.questionnaire.get(question, {}).get("tags", []) if t not in out)
        return out
