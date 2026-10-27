from django.test import TestCase, override_settings


class HealthzTests(TestCase):
    @override_settings(LAWHUB_PRIVATE=True)
    def test_healthz_needs_no_login_or_database(self):
        with self.assertNumQueries(0):
            response = self.client.get("/healthz")
        self.assertEqual(response.content, b"ok")
