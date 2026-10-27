from django.db import models
from django.urls import reverse


class Tag(models.Model):
    """A topic in the tag tree; a tag with children doubles as a category.

    Slugs are dotted paths ("transport.vehicles.inspection"), so following
    "transport.vehicles" covers every tag below it.
    """

    slug = models.CharField(max_length=200, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    name_pl = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.name_pl

    def get_absolute_url(self):
        return reverse("tags:detail", args=[self.slug])

    def subtree_q(self, prefix="slug"):
        """Q matching this tag and every tag below it (`prefix` is the slug lookup path)."""
        return models.Q(**{prefix: self.slug}) | models.Q(**{f"{prefix}__startswith": f"{self.slug}."})


class ProvisionTag(models.Model):
    """A tag applied directly to a provision.

    Tags inherit down the provision tree when read, so tagging an article
    (or the chapter heading above it) covers all of its paragraphs.
    """

    class Source(models.TextChoices):
        RULE = "rule", "Reguła"
        MANUAL = "manual", "Ręcznie"
        LLM = "llm", "Model językowy"

    provision = models.ForeignKey("laws.Provision", on_delete=models.CASCADE, related_name="tag_links")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="provision_links")
    source = models.CharField(max_length=20, choices=Source.choices)
    confidence = models.FloatField(default=1.0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provision", "tag"], name="unique_provision_tag")]

    def __str__(self):
        return f"{self.tag.slug} → {self.provision}"
