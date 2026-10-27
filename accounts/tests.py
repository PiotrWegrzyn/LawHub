import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Subscription
from laws.services import import_act_text
from laws.sources import nalegalu

FIXTURES = Path(__file__).resolve().parent.parent / "laws" / "tests" / "fixtures" / "nalegalu"


class QuestionnaireTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with override_settings(LAWHUB_LAW_REPO=Path(self.tmp.name)):
            import_act_text(nalegalu.load_act(nalegalu.find_act_dir(FIXTURES, "DU/2099/1")), source="nalegalu")
        self.user = User.objects.create_user("jan", password="haslo-testowe-123")
        self.client.force_login(self.user)

    def tearDown(self):
        self.tmp.cleanup()

    def test_questionnaire_suggests_tag_subscriptions(self):
        self.client.post(reverse("accounts:questionnaire"), {"has_car": "on", "city": "Kraków"})
        slugs = set(Subscription.objects.filter(user=self.user).values_list("tag__slug", flat=True))
        self.assertIn("transport.vehicles.inspection", slugs)
        self.assertTrue(Subscription.objects.filter(user=self.user, origin=Subscription.Origin.QUESTIONNAIRE).exists())
        self.assertEqual(self.user.profile.city, "Kraków")

    def test_retaking_questionnaire_keeps_manual_subscriptions(self):
        self.client.post(reverse("accounts:follow_tag", args=["transport.road.cycling"]))
        self.client.post(reverse("accounts:questionnaire"), {"has_car": "on"})
        self.client.post(reverse("accounts:questionnaire"), {"walks": "on"})
        slugs = set(Subscription.objects.filter(user=self.user).values_list("tag__slug", flat=True))
        self.assertEqual(slugs, {"transport.road.cycling", "transport.road.pedestrians"})

    def test_pages_render(self):
        for url in [
            reverse("laws:home"),
            reverse("laws:act", args=["pl", "DU/2099/1"]),
            reverse("laws:search") + "?q=prędkość",
            reverse("tags:list"),
            reverse("tags:detail", args=["transport.vehicles"]),
            reverse("accounts:subscriptions"),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
