"""Import an act version into the law repo and the database.

Flow: ActText (from any source) -> git commit -> DB rows -> tags -> ChangeReport.
The ChangeReport lists provisions added, removed or reworded relative to the
act's previous version; it is what will drive subscriber notifications.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.db import transaction

from laws.domain.units import ActText
from laws.gitstore import GitStore
from laws.models import Act, ActVersion, Jurisdiction, Provision, ProvisionText
from tags.models import ProvisionTag, Tag
from tags.tagger import TagRules

JURISDICTION_NAMES = {"pl": "Polska", "eu": "Unia Europejska"}

# "<future wording>" / "[replaced wording]" markers in Sejm unified texts.
_PENDING = re.compile(r"<[^<>]{2,}>?|\[[^\[\]]{2,}\]")


@dataclass
class ChangeReport:
    act: Act
    version: ActVersion
    is_new_version: bool
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)


def import_act_text(text: ActText, *, source: str, store: GitStore | None = None, rules: TagRules | None = None) -> ChangeReport:
    store = store or GitStore(settings.LAWHUB_LAW_REPO)
    units = list(text.root.walk())
    content_hash = hashlib.sha256(
        "\n".join(f"{u.address}\x1f{u.content_hash()}" for u, _ in units).encode()
    ).hexdigest()

    with transaction.atomic():
        jurisdiction, _ = Jurisdiction.objects.get_or_create(
            code=text.act.jurisdiction, defaults={"name": JURISDICTION_NAMES.get(text.act.jurisdiction, text.act.jurisdiction)}
        )
        act, _ = Act.objects.update_or_create(
            jurisdiction=jurisdiction,
            source_id=text.act.source_id,
            defaults=_act_fields(text),
        )
        existing = act.versions.filter(content_hash=content_hash).first()
        if existing:
            return ChangeReport(act, existing, is_new_version=False)

        previous = act.versions.filter(is_current=True).first()
        commit = store.write_version(text)
        act.versions.update(is_current=False)
        version = ActVersion.objects.create(
            act=act,
            version_id=text.version_id,
            version_date=date.fromisoformat(text.version_date),
            label=text.version_label,
            source=source,
            content_hash=content_hash,
            git_commit=commit.sha,
            is_current=True,
        )

        provisions = {p.address: p for p in act.provisions.all()}
        new = [Provision(act=act, address=u.address, kind=u.kind) for u, _ in units if u.address not in provisions]
        for p in Provision.objects.bulk_create(new):
            provisions[p.address] = p
        # Parent links follow the document tree (article -> chapter -> act).
        changed_parents = []
        for unit, _ in units:
            for child in unit.children:
                prov = provisions[child.address]
                if prov.parent_id != provisions[unit.address].id:
                    prov.parent_id = provisions[unit.address].id
                    changed_parents.append(prov)
        Provision.objects.bulk_update(changed_parents, ["parent"], batch_size=1000)

        ProvisionText.objects.bulk_create(
            [
                ProvisionText(
                    provision=provisions[unit.address],
                    version=version,
                    ordinal=ordinal,
                    depth=depth,
                    label=unit.label,
                    heading=unit.heading or "",
                    text=unit.text,
                    tail=unit.tail,
                    content_hash=unit.content_hash(),
                    has_pending_change=bool(_PENDING.search(f"{unit.heading or ''} {unit.text} {unit.tail}")),
                )
                for ordinal, (unit, depth) in enumerate(units)
            ],
            batch_size=1000,
        )

        apply_rule_tags(text, provisions, rules or TagRules.load())

        report = ChangeReport(act, version, is_new_version=True)
        if previous:
            before = dict(previous.provision_texts.values_list("provision__address", "content_hash"))
            after = dict(version.provision_texts.values_list("provision__address", "content_hash"))
            report.added = sorted(a for a in after if a not in before)
            report.removed = sorted(a for a in before if a not in after)
            report.modified = sorted(a for a in after if a in before and after[a] != before[a])
        return report


def _act_fields(text: ActText) -> dict:
    meta = text.act
    return {
        "title": meta.title,
        "native_type": meta.native_type,
        "act_type": meta.act_type,
        "status": meta.status or "",
        "in_force": meta.in_force,
        "published_on": date.fromisoformat(meta.published_on) if meta.published_on else None,
        "display_address": meta.display_address or "",
        "source_url": meta.source_url or "",
        "keywords": meta.keywords,
        "repo_path": GitStore.act_path(text),
    }


def sync_tag_tree(rules: TagRules) -> dict[str, Tag]:
    tags = {t.slug: t for t in Tag.objects.all()}
    for slug, names in rules.tags.items():
        tag = tags.get(slug) or Tag(slug=slug)
        tag.name_pl, tag.name_en = names.get("pl", slug), names.get("en", "")
        tag.save()
        tags[slug] = tag
    for slug, tag in tags.items():
        parent = tags.get(slug.rpartition(".")[0])
        if parent and tag.parent_id != parent.id:
            tag.parent = parent
            tag.save(update_fields=["parent"])
    return tags


def apply_rule_tags(text: ActText, provisions: dict[str, Provision], rules: TagRules) -> None:
    """Recompute rule-based tags for one act; manual and LLM tags are left alone."""
    tags = sync_tag_tree(rules)
    act_id = provisions[""].act_id
    ProvisionTag.objects.filter(provision__act_id=act_id, source=ProvisionTag.Source.RULE).delete()
    ProvisionTag.objects.bulk_create(
        [
            ProvisionTag(provision=provisions[address], tag=tags[slug], source=ProvisionTag.Source.RULE)
            for address, slugs in rules.tag(text).items()
            for slug in sorted(slugs)
        ],
        ignore_conflicts=True,  # a manual tag may already cover the same pair
    )
