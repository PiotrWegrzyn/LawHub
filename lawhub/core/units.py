"""Jurisdiction-neutral representation of a legal text.

Every source (Polish ELI, EUR-Lex, legislation.gov.uk, ...) parses its native
format into a tree of `Unit`s. Everything downstream - the git renderer, the
database, the tagger, change detection - only ever sees this tree, so adding a
country means writing a fetcher and a parser, nothing else.

Each unit gets a stable *address* (e.g. ``art_5/par_1/pt_2/lit_a``) that stays
the same across versions of the act. Tags and subscriptions hang off
(act, address), which is what lets us say "paragraph X changed" between two
versions of a law.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterator

# Generic unit kinds, ordered from the outermost to the innermost.
# Native names map onto these (PL: Dział -> division, ustęp/§ -> paragraph, ...).
KIND_RANK = {
    "act": 0,
    "part": 1,
    "book": 2,
    "title": 3,
    "division": 4,
    "chapter": 5,
    "section": 6,
    "article": 7,
    "paragraph": 8,
    "point": 9,
    "letter": 10,
    "indent": 11,
}

KIND_ABBR = {
    "part": "part",
    "book": "book",
    "title": "tit",
    "division": "div",
    "chapter": "chp",
    "section": "sec",
    "article": "art",
    "paragraph": "par",
    "point": "pt",
    "letter": "lit",
    "indent": "ind",
}

# Structural containers (chapters etc.) group articles but are not part of an
# article's address: article numbers are unique within an act, so
# "art_5" stays valid even if a chapter is renumbered.
CONTAINER_KINDS = {"part", "book", "title", "division", "chapter", "section"}


@dataclass
class Unit:
    kind: str
    number: str | None = None
    label: str = ""  # as printed in the source, e.g. "Art. 5a.", "§ 2.", "3)"
    heading: str | None = None  # e.g. chapter title "Przepisy ogólne"
    text: str = ""  # the unit's own text (intro before any sub-units)
    tail: str = ""  # wrap-up text after the sub-units ("- podlega karze grzywny")
    children: list[Unit] = field(default_factory=list)
    address: str = ""

    @property
    def rank(self) -> int:
        return KIND_RANK[self.kind]

    def walk(self, depth: int = 0) -> Iterator[tuple[Unit, int]]:
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)

    def content_hash(self) -> str:
        """Hash of this unit's own wording (not its children)."""
        payload = "\x1f".join([self.label, self.heading or "", self.text, self.tail])
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def assign_addresses(root: Unit) -> None:
    """Fill in `address` for every unit in the tree, keeping them unique."""
    seen: dict[str, int] = {}

    def visit(unit: Unit, container_path: str, provision_path: str) -> None:
        for idx, child in enumerate(unit.children, start=1):
            seg = f"{KIND_ABBR[child.kind]}_{child.number or idx}"
            if child.kind in CONTAINER_KINDS:
                base = f"{container_path}/{seg}" if container_path else seg
                next_container, next_provision = base, ""
            elif child.kind == "article":
                base = seg
                next_container, next_provision = container_path, base
            else:
                base = f"{provision_path}/{seg}" if provision_path else seg
                next_container, next_provision = container_path, base
            # Parser hiccups or genuinely duplicated numbering must not collide.
            n = seen.get(base, 0) + 1
            seen[base] = n
            child.address = base if n == 1 else f"{base}~{n}"
            if child.kind not in CONTAINER_KINDS:
                next_provision = child.address
            visit(child, next_container, next_provision)

    root.address = ""
    visit(root, "", "")


@dataclass
class ActMetadata:
    """Source-independent metadata about one act."""

    jurisdiction: str  # ISO 3166-1 alpha-2 ("pl"), or "eu", later "pl-12" for regions
    source_id: str  # the source's own stable id, e.g. ELI "DU/1997/602"
    title: str
    native_type: str  # "Ustawa", "Rozporządzenie", ...
    act_type: str  # normalized: statute | regulation | code | notice | other
    status: str | None = None
    in_force: bool | None = None
    published_on: str | None = None  # ISO dates
    in_force_from: str | None = None
    keywords: list[str] = field(default_factory=list)
    source_url: str | None = None
    display_address: str | None = None  # "Dz.U. 1997 nr 98 poz. 602"
    raw: dict = field(default_factory=dict)


@dataclass
class ActText:
    """One concrete wording of an act (original or consolidated)."""

    act: ActMetadata
    version_id: str  # id of the document the text came from, e.g. "DU/2024/1251"
    version_date: str  # date the wording is valid from / was published (ISO)
    version_label: str  # "tekst jednolity Dz.U. 2024 poz. 1251"
    root: Unit
