from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    # Raw questionnaire answers, e.g. {"has_car": true}; kept so suggestions
    # can be recomputed when the questionnaire or tag rules change.
    answers = models.JSONField(default=dict, blank=True)
    city = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Profil {self.user}"


class Subscription(models.Model):
    """A user follows exactly one of: a tag (and everything under it), an act, or a provision."""

    class Origin(models.TextChoices):
        MANUAL = "manual", "Dodane ręcznie"
        QUESTIONNAIRE = "questionnaire", "Z ankiety"
        AI = "ai", "Dodane przez AI"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    tag = models.ForeignKey("tags.Tag", null=True, blank=True, on_delete=models.CASCADE)
    act = models.ForeignKey("laws.Act", null=True, blank=True, on_delete=models.CASCADE)
    provision = models.ForeignKey("laws.Provision", null=True, blank=True, on_delete=models.CASCADE)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tag__isnull=False, act__isnull=True, provision__isnull=True)
                    | models.Q(tag__isnull=True, act__isnull=False, provision__isnull=True)
                    | models.Q(tag__isnull=True, act__isnull=True, provision__isnull=False)
                ),
                name="subscription_has_one_target",
            ),
            models.UniqueConstraint(fields=["user", "tag"], name="unique_tag_subscription"),
            models.UniqueConstraint(fields=["user", "act"], name="unique_act_subscription"),
            models.UniqueConstraint(fields=["user", "provision"], name="unique_provision_subscription"),
        ]

    def __str__(self):
        return f"{self.user} → {self.target}"

    @property
    def target(self):
        return self.tag or self.act or self.provision
