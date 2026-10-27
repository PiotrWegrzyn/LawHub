"""Acts, their versions and their provisions.

The git repository of rendered acts is the source of truth for *wording*; the
database indexes it so the site can browse, tag, subscribe and notify.

Core idea: a `Provision` is a stable identity, (act, address), e.g.
(Prawo o ruchu drogowym, "art_81/par_6"). Its wording lives in
`ProvisionText` rows, one per `ActVersion`. Tags and subscriptions attach to
the stable `Provision`, so they survive new versions of the act, and
comparing ProvisionText hashes between versions tells us exactly which
provisions changed and therefore whom to notify.
"""

from django.db import models
from django.urls import reverse

from laws.domain.units import CONTAINER_KINDS


class Jurisdiction(models.Model):
    """A country, supranational body or region: "pl", "eu", later "pl-12"."""

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")

    def __str__(self):
        return self.name


class Act(models.Model):
    """One legal act, independent of how many versions of its text exist."""

    class ActType(models.TextChoices):
        STATUTE = "statute", "Ustawa"
        CODE = "code", "Kodeks"
        REGULATION = "regulation", "Rozporządzenie"
        CONSOLIDATED_TEXT = "consolidated_text", "Tekst jednolity"
        NOTICE = "notice", "Obwieszczenie"
        TREATY = "treaty", "Umowa międzynarodowa"
        COURT_RULING = "court_ruling", "Orzeczenie"
        OTHER = "other", "Inne"

    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT, related_name="acts")
    source_id = models.CharField(max_length=100, help_text='Source identifier, for Poland the ELI, e.g. "DU/1997/602".')
    title = models.TextField()
    native_type = models.CharField(max_length=100)
    act_type = models.CharField(max_length=40, choices=ActType.choices)
    status = models.CharField(max_length=100, blank=True)
    in_force = models.BooleanField(null=True)
    published_on = models.DateField(null=True, blank=True)
    display_address = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    repo_path = models.CharField(max_length=300, help_text="Directory of this act in the law git repository.")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["jurisdiction", "source_id"], name="unique_act_per_jurisdiction")]
        ordering = ["title"]

    def __str__(self):
        return self.display_address or self.source_id

    def get_absolute_url(self):
        return reverse("laws:act", args=[self.jurisdiction.code, self.source_id])

    @property
    def current_version(self):
        return self.versions.filter(is_current=True).first()


class ActVersion(models.Model):
    """One wording of an act: the original, a consolidated text, a snapshot."""

    act = models.ForeignKey(Act, on_delete=models.CASCADE, related_name="versions")
    version_id = models.CharField(max_length=100, help_text='e.g. "DU/2024/1251" or "nalegalu:DU/1997/602".')
    version_date = models.DateField()
    label = models.TextField()
    source = models.CharField(max_length=40, help_text='Where the text came from: "nalegalu", "eli", ...')
    content_hash = models.CharField(max_length=64)
    git_commit = models.CharField(max_length=64, blank=True)
    is_current = models.BooleanField(default=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["act", "content_hash"], name="unique_version_content")]
        ordering = ["act", "version_date"]

    def __str__(self):
        return f"{self.act} – {self.label}"


class Provision(models.Model):
    """Stable identity of a unit of an act (article, paragraph, point, ...) across versions."""

    CONTAINER_KINDS = frozenset(CONTAINER_KINDS)

    act = models.ForeignKey(Act, on_delete=models.CASCADE, related_name="provisions")
    address = models.CharField(max_length=300, help_text='e.g. "art_81/par_6"; empty for the act itself.')
    kind = models.CharField(max_length=20)
    # Follows the document tree: an article's parent is its chapter, so it
    # inherits the chapter's tags even though chapters aren't in its address.
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["act", "address"], name="unique_provision_address")]

    def __str__(self):
        return f"{self.act} {self.address or '(cały akt)'}"

    def get_absolute_url(self):
        return f"{self.act.get_absolute_url()}#{self.anchor}"

    @property
    def is_container(self):
        return self.kind in self.CONTAINER_KINDS

    @property
    def anchor(self):
        return self.address.replace("/", "-") or "top"

    def ancestors(self):
        """This provision and every parent up to the act root."""
        node = self
        while node is not None:
            yield node
            node = node.parent


class ProvisionText(models.Model):
    """Wording of a provision in one act version."""

    provision = models.ForeignKey(Provision, on_delete=models.CASCADE, related_name="texts")
    version = models.ForeignKey(ActVersion, on_delete=models.CASCADE, related_name="provision_texts")
    ordinal = models.PositiveIntegerField(help_text="Document order within the version.")
    depth = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=100)
    heading = models.TextField(blank=True)
    text = models.TextField(blank=True)
    tail = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    # Source marks wording that is not yet / no longer in force
    # (Sejm "<future wording>" and "[replaced wording]" markers).
    has_pending_change = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provision", "version"], name="unique_text_per_version")]
        ordering = ["version", "ordinal"]

    def __str__(self):
        return f"{self.provision} @ {self.version.version_id}"
