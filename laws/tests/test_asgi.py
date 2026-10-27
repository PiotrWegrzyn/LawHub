import asyncio

from django.test import SimpleTestCase

from config.asgi import application


class AsgiHealthzTests(SimpleTestCase):
    def test_healthz_bypasses_django_host_check(self):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "path": "/healthz", "method": "GET", "headers": [(b"host", b"10.0.0.7:8080")]}
        asyncio.run(application(scope, receive, send))
        self.assertEqual(sent[0]["status"], 200)
        self.assertEqual(sent[1]["body"], b"ok")
