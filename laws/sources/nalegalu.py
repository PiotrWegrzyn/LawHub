"""Import Polish acts from a local checkout of the nalegalu dataset.

nalegalu (https://github.com/nalegaluorg/nalegalu, CC0) publishes ~20k Polish
acts as Markdown, one directory per act named after its ISAP address::

    inne/WDU19970980602/index.md

Each ``index.md`` has YAML frontmatter followed by the act text in a fairly
regular Markdown dialect:

    #### Rozdział 1 Przepisy ogólne        <- containers as headings
    **Art. 5.** Optional text             <- articles (regulations: **§ 5.**)
    1. Text                               <- ustęp; in codes "§ 1. Text"
    - **1)** text                         <- punkt
        - **a)** text                     <- litera
            - text                        <- tiret

The text is mostly extracted from PDFs, so it carries PDF artifacts (stray
wrapped fragments, footnote bleed). We repair the cheap ones and record the
source as lower-quality so the official ELI pipeline can replace it later.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from laws.domain.units import ActMetadata, ActText, Unit, assign_addresses
from laws.sources.pl import normalize_act_type

SOURCE_NAME = "nalegalu"

_NUM = r"\d+[a-z]*(?:[¹²³⁴⁵⁶⁷⁸⁹⁰]+)?"

_CONTAINERS = [
    (re.compile(r"^(?:CZĘŚĆ|Część)\s+(\S+)\s*(.*)$"), "part"),
    (re.compile(r"^(?:KSIĘGA|Księga)\s+(\S+)\s*(.*)$"), "book"),
    (re.compile(r"^(?:TYTUŁ|Tytuł)\s+([IVXLC]+[a-z]*)\b\s*(.*)$"), "title"),
    (re.compile(r"^(?:DZIAŁ|Dział)\s+([IVXLC]+[a-z]*|\d+[a-z]*)\b\s*(.*)$"), "division"),
    (re.compile(r"^(?:ROZDZIAŁ|Rozdział)\s+([IVXLC]+[a-z]*|\d+[a-z]*)\b\s*(.*)$"), "chapter"),
    (re.compile(r"^(?:ODDZIAŁ|Oddział)\s+(\d+[a-z]*)\b\s*(.*)$"), "section"),
]
# Unnumbered part headings in codes, e.g. "## CZĘŚĆ OGÓLNA".
_NAMED_PART = re.compile(r"^(?:CZĘŚĆ|Część)\s+(OGÓLNA|SZCZEGÓLNA|WOJSKOWA)\b\s*(.*)$", re.I)

_HEADING = re.compile(r"^(#{2,6})\s+(.*)$")
_ARTICLE = re.compile(rf"^\*\*Art\.\s*({_NUM})\.\*\*\s*(.*)$")
_TOP_PARAGRAPH = re.compile(rf"^\*\*§\s*({_NUM})\.\*\*\s*(.*)$")
_PARAGRAPH = re.compile(rf"^(?:§\s*)?({_NUM})\.(?:\s+(.*)|$)")
_LIST_ITEM = re.compile(r"^( *)- (?:\*\*([^*]+)\*\*\s*)?(.*)$")
_POINT_LABEL = re.compile(rf"^({_NUM})\)$")
_LETTER_LABEL = re.compile(r"^([a-z]{1,3})\)$")

# A paragraph/point that is just a bare number right after text ending like
# "z zastrzeżeniem art. 33 ust." is a PDF line-wrap, not a new unit.
_DANGLING_REF = re.compile(r"(?:\b(?:art|ust|pkt|lit|poz|nr)\.?|§)\s*$")


def find_act_dir(root: Path, eli: str) -> Path:
    """Locate an act directory from its ELI id, e.g. "DU/1997/602"."""
    publisher, year, pos = eli.strip("/").split("/")
    prefix = {"DU": "WDU", "MP": "WMP"}[publisher.upper()]
    # ISAP address: W + DU + year + 3-digit journal number + 4-digit position.
    matches = sorted(root.glob(f"*/{prefix}{year}???{int(pos):04d}"))
    if not matches:
        raise FileNotFoundError(f"{eli} not found in nalegalu checkout {root}")
    return matches[0]


def load_act(act_dir: Path) -> ActText:
    raw = (act_dir / "index.md").read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw)
    act = _metadata(meta, body)
    root = parse_body(body)
    root.heading = act.title
    return ActText(
        act=act,
        version_id=f"{SOURCE_NAME}:{act.source_id}",
        version_date=_table_field(body, "Ostatnia zmiana") or act.published_on or "1970-01-01",
        version_label=f"nalegalu snapshot ({_table_field(body, 'Ostatnia zmiana') or 'undated'})",
        root=root,
    )


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    _, fm, body = raw.split("---", 2)
    return yaml.safe_load(fm) or {}, body


def _table_field(body: str, name: str) -> str | None:
    m = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*(.*?)\s*\|\s*$", body, re.M)
    return m.group(1) if m else None


def _metadata(fm: dict, body: str) -> ActMetadata:
    eli = fm.get("eli") or ""
    native_type = fm.get("act_type") or ""
    in_force = _table_field(body, "W mocy")
    return ActMetadata(
        jurisdiction="pl",
        source_id=eli,
        title=str(fm.get("title", "")).strip().rstrip("."),
        native_type=native_type,
        act_type=normalize_act_type(native_type, str(fm.get("title", ""))),
        status=fm.get("status"),
        in_force=None if in_force is None else in_force.lower() == "tak",
        published_on=_table_field(body, "Data ogłoszenia"),
        in_force_from=_table_field(body, "Data wydania"),
        source_url=f"https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id={fm.get('address')}",
        display_address=_table_field(body, "Adres publikacyjny"),
        raw={"nalegalu": fm},
    )


def parse_body(body: str) -> Unit:
    """Parse the Markdown body of an act into a Unit tree."""
    root = Unit(kind="act")
    stack: list[Unit] = [root]
    started = False  # skip the title block and metadata table
    preamble: list[str] = []
    pending_heading: Unit | None = None

    def push(unit: Unit) -> None:
        nonlocal pending_heading
        while len(stack) > 1 and stack[-1].rank >= unit.rank:
            stack.pop()
        stack[-1].children.append(unit)
        stack.append(unit)
        pending_heading = None

    def append_text(text: str) -> None:
        cur = stack[-1]
        if cur.children:
            cur.tail = f"{cur.tail} {text}".strip()
        else:
            cur.text = f"{cur.text} {text}".strip()

    for raw_line in body.splitlines():
        line = raw_line.rstrip().replace(" ", " ")
        if not line.strip():
            continue
        stripped = line.strip()

        if m := _HEADING.match(stripped):
            text = m.group(2).strip()
            container = _container(text)
            if container:
                started = True
                push(container)
                pending_heading = container if not container.heading else None
            elif started:
                append_text(text)
            continue

        if m := _ARTICLE.match(stripped):
            started = True
            push(Unit("article", m.group(1), f"Art. {m.group(1)}."))
            _inline_paragraph(m.group(2), push, append_text)
            continue

        if m := _TOP_PARAGRAPH.match(stripped):
            started = True
            # Regulations use "§ N." as their basic unit, i.e. at article level.
            push(Unit("article", m.group(1), f"§ {m.group(1)}.", segment=f"par_{m.group(1)}"))
            _inline_paragraph(m.group(2), push, append_text)
            continue

        if not started:
            if not stripped.startswith(("|", "*")) and not stripped.startswith("# "):
                preamble.append(stripped)
            continue

        if pending_heading is not None and not _PARAGRAPH.match(stripped) and not line.lstrip().startswith("- "):
            pending_heading.heading = f"{pending_heading.heading or ''} {stripped}".strip()
            continue

        if (m := _LIST_ITEM.match(line)) and _inside_provision(stack):
            indent, label, text = len(m.group(1)), (m.group(2) or "").strip(), m.group(3).strip()
            if pm := _POINT_LABEL.match(label):
                unit = Unit("point", pm.group(1), label, text=text)
            elif lm := _LETTER_LABEL.match(label):
                unit = Unit("letter", lm.group(1), label, text=text)
            elif not label and indent >= 8:
                unit = Unit("indent", None, "–", text=text.lstrip("–- ").strip())
            else:
                append_text(f"{label} {text}".strip())
                continue
            push(unit)
            continue

        if (m := _PARAGRAPH.match(stripped)) and _inside_provision(stack):
            number, text = m.group(1), (m.group(2) or "").strip()
            if not text and _DANGLING_REF.search(_last_text(stack)):
                append_text(f"{number}.")  # "... art. 33 ust." + "1." is one sentence
                continue
            label = f"§ {number}." if stripped.startswith("§") else f"{number}."
            push(Unit("paragraph", number, label, text=text))
            continue

        append_text(stripped)

    root.text = " ".join(preamble)
    assign_addresses(root)
    return root


def _container(text: str) -> Unit | None:
    if m := _NAMED_PART.match(text):
        return Unit("part", m.group(1).lower(), f"Część {m.group(1).lower()}", heading=m.group(2) or None)
    for pattern, kind in _CONTAINERS:
        if m := pattern.match(text):
            label = text[: m.start(2)].strip() if m.group(2) else text.strip()
            return Unit(kind, m.group(1), label, heading=m.group(2).strip() or None)
    return None


def _inside_provision(stack: list[Unit]) -> bool:
    return any(u.kind == "article" for u in stack)


def _last_text(stack: list[Unit]) -> str:
    cur = stack[-1]
    return cur.tail or cur.text


def _inline_paragraph(rest: str, push, append_text) -> None:
    """Handle text on the same line as the article header ("Art. 5. 1. Text")."""
    rest = rest.strip()
    if not rest:
        return
    if (m := _PARAGRAPH.match(rest)) and m.group(2):
        label = f"§ {m.group(1)}." if rest.startswith("§") else f"{m.group(1)}."
        push(Unit("paragraph", m.group(1), label, text=m.group(2).strip()))
    else:
        append_text(rest)
