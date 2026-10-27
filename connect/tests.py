import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model

from accounts.forms import SignupForm
from accounts.models import Subscription
from connect import mcp_server
from laws.services import import_act_text
from laws.sources import nalegalu

FIXTURES = Path(__file__).resolve().parent.parent / "laws" / "tests" / "fixtures" / "nalegalu"


class OAuthEndpointsTests(TestCase):
    def test_authorization_server_metadata(self):
        meta = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertTrue(meta["authorization_endpoint"].endswith("/o/authorize/"))
        self.assertTrue(meta["registration_endpoint"].endswith("/connect/register/"))
        self.assertEqual(meta["code_challenge_methods_supported"], ["S256"])

    def test_dynamic_client_registration(self):
        response = self.client.post(
            "/connect/register/",
            {"client_name": "Claude", "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        app = get_application_model().objects.get(client_id=response.json()["client_id"])
        self.assertEqual(app.client_type, "public")

    def test_registration_rejects_non_https_redirects(self):
        response = self.client.post(
            "/connect/register/", {"redirect_uris": ["http://evil.example/cb"]}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)


class McpToolTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        repo = override_settings(LAWHUB_LAW_REPO=Path(self.tmp.name))
        repo.enable()
        self.addCleanup(repo.disable)
        import_act_text(self._fixture(), source="nalegalu")
        self.user = User.objects.create_user("ola", password="x")
        patcher = mock.patch.object(mcp_server, "_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _fixture():
        return nalegalu.load_act(nalegalu.find_act_dir(FIXTURES, "DU/2099/1"))

    def test_token_verifier_maps_token_to_user(self):
        app = get_application_model().objects.create(
            name="t", client_type="public", authorization_grant_type="authorization-code", redirect_uris="https://x/cb"
        )
        get_access_token_model().objects.create(
            user=self.user, application=app, token="secret-token", scope="lawhub", expires=timezone.now() + timedelta(hours=1)
        )
        # The async verify_token only wraps _verify in sync_to_async, whose second
        # DB connection can't see this test's transaction.
        verifier = mcp_server.DjangoOAuthTokenVerifier()
        self.assertEqual(verifier._verify("secret-token").subject, str(self.user.pk))
        self.assertIsNone(verifier._verify("wrong"))

    def test_search_and_get_provision(self):
        hits = mcp_server._search_law("prędkość", 5)
        self.assertEqual(hits[0]["address"], "art_4")
        prov = mcp_server._get_provision("DU/2099/1", "art_2")
        self.assertIn("badania technicznego", prov["text"])
        self.assertIn("transport.vehicles.inspection", prov["topics"])

    def test_follow_and_unfollow_topics(self):
        result = mcp_server._follow_topics(["transport.road.speed", "no.such.topic"])
        self.assertEqual(result["followed"], ["transport.road.speed"])
        self.assertEqual(result["unknown"], ["no.such.topic"])
        self.assertEqual(Subscription.objects.get(user=self.user).origin, Subscription.Origin.AI)
        mcp_server._unfollow_topics(["transport.road.speed"])
        self.assertFalse(Subscription.objects.filter(user=self.user).exists())

    def test_recent_changes_reports_reworded_followed_provisions(self):
        mcp_server._follow_topics(["transport.road.speed"])
        text = self._fixture()
        units = {u.address: u for u, _ in text.root.walk()}
        units["art_4"].text = "Kto przekracza dopuszczalną prędkość o ponad 50 km/h, podlega karze grzywny."
        units["art_1"].text = "Ustawa określa zasady ruchu i kary."  # changed, but not in a followed topic
        text.version_date = "2099-06-01"
        import_act_text(text, source="nalegalu")
        changes = mcp_server._recent_changes(30)
        self.assertEqual([(c["address"], c["change"]) for c in changes], [("art_4", "modified")])


class SignupAllowlistTests(TestCase):
    def test_signup_requires_allowlisted_email(self):
        data = {"username": "a", "email": "A@Example.com", "password1": "dlugie-haslo-123", "password2": "dlugie-haslo-123"}
        self.assertTrue(SignupForm(data, allowlist={"a@example.com"}).is_valid())
        self.assertFalse(SignupForm(data, allowlist={"b@example.com"}).is_valid())
