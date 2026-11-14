import os
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from Routes.auth import router
from Services import supabase_auth_service


class GoogleAuthRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    def test_google_login_returns_supabase_pkce_url(self):
        challenge = "A" * 43
        url = "https://project.supabase.co/auth/v1/authorize"
        with patch.object(
            supabase_auth_service,
            "google_authorization_url",
            return_value=url,
        ) as authorize:
            response = self.client.get(
                "/auth/google",
                params={"code_challenge": challenge},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authorization_url": url})
        authorize.assert_called_once_with(challenge)

    def test_google_callback_exchanges_code_and_verifier(self):
        session = {"access_token": "access", "user": {"id": "user-id"}}
        with patch.object(
            supabase_auth_service,
            "exchange_google_code",
            new_callable=AsyncMock,
            return_value=session,
        ) as exchange:
            response = self.client.post(
                "/auth/google/callback",
                json={"code": "one-time-code", "code_verifier": "v" * 43},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), session)
        exchange.assert_awaited_once_with("one-time-code", "v" * 43)

    def test_callback_rejects_invalid_verifier(self):
        response = self.client.post(
            "/auth/google/callback",
            json={"code": "one-time-code", "code_verifier": "short"},
        )
        self.assertEqual(response.status_code, 422)


class GoogleAuthServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_authorization_url_uses_configured_callback_and_pkce(self):
        with (
            patch.object(
                supabase_auth_service,
                "_settings",
                return_value=("https://project.supabase.co", "public-key"),
            ),
            patch.dict(
                os.environ,
                {"FRONTEND_AUTH_CALLBACK_URL": "https://app.example.com/auth/callback"},
            ),
        ):
            url = supabase_auth_service.google_authorization_url("A" * 43)

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/auth/v1/authorize")
        self.assertEqual(query["provider"], ["google"])
        self.assertEqual(query["redirect_to"], ["https://app.example.com/auth/callback"])
        self.assertEqual(query["code_challenge"], ["A" * 43])
        self.assertEqual(query["code_challenge_method"], ["s256"])

    def test_authorization_url_rejects_non_https_remote_callback(self):
        with (
            patch.object(
                supabase_auth_service,
                "_settings",
                return_value=("https://project.supabase.co", "public-key"),
            ),
            patch.dict(
                os.environ,
                {"FRONTEND_AUTH_CALLBACK_URL": "http://app.example.com/auth/callback"},
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            supabase_auth_service.google_authorization_url("A" * 43)

        self.assertEqual(raised.exception.status_code, 503)

    async def test_exchange_uses_supabase_pkce_token_endpoint(self):
        expected = {"access_token": "access", "user": {"id": "user-id"}}
        with patch.object(
            supabase_auth_service,
            "_request",
            new_callable=AsyncMock,
            return_value=expected,
        ) as request:
            result = await supabase_auth_service.exchange_google_code(
                "one-time-code",
                "v" * 43,
            )

        self.assertEqual(result, expected)
        request.assert_awaited_once_with(
            "POST",
            "/token?grant_type=pkce",
            payload={"auth_code": "one-time-code", "code_verifier": "v" * 43},
            invalid_credentials=True,
            invalid_credentials_message="El código de Google no es válido o expiró.",
        )


if __name__ == "__main__":
    unittest.main()
