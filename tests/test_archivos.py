import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from Routes.archivos import require_authenticated_context, router
from Services import storage_service


class ArchivosRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.user_id = str(uuid4())
        self.app.dependency_overrides[require_authenticated_context] = lambda: {
            "user": {"id": self.user_id},
            "access_token": "test-token",
        }
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    def test_upload_file(self):
        metadata = {"id": str(uuid4()), "category": "project_document"}
        with patch.object(
            storage_service, "upload_file", new_callable=AsyncMock, return_value=metadata
        ) as upload:
            response = self.client.post(
                "/archivos",
                params={
                    "tipo_entidad": "proyecto",
                    "id_entidad": str(uuid4()),
                    "categoria": "project_document",
                },
                files={"file": ("memoria.pdf", b"%PDF-1.7 ejemplo", "application/pdf")},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), metadata)
        self.assertEqual(upload.await_args.kwargs["access_token"], "test-token")

    def test_upload_over_limit_is_rejected(self):
        with patch("Routes.archivos.MAX_UPLOAD_BYTES", 4):
            response = self.client.post(
                "/archivos",
                params={
                    "tipo_entidad": "proyecto",
                    "id_entidad": str(uuid4()),
                    "categoria": "project_document",
                },
                files={"file": ("memoria.pdf", b"12345", "application/pdf")},
            )
        self.assertEqual(response.status_code, 413)

    def test_list_signed_url_and_delete_routes(self):
        file_id = uuid4()
        with (
            patch.object(storage_service, "list_files", return_value=[]) as list_files,
            patch.object(
                storage_service,
                "create_signed_url",
                new_callable=AsyncMock,
                return_value={"id": str(file_id), "url": "https://example.test/signed"},
            ) as signed_url,
            patch.object(
                storage_service,
                "delete_file",
                new_callable=AsyncMock,
                return_value=str(file_id),
            ) as delete_file,
        ):
            listing = self.client.get(
                "/archivos",
                params={"tipo_entidad": "lote", "id_entidad": str(uuid4())},
            )
            signed = self.client.get(f"/archivos/{file_id}/url")
            deleted = self.client.delete(f"/archivos/{file_id}")

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(signed.status_code, 200)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(list_files.call_args.kwargs["user_id"].hex, self.user_id.replace("-", ""))
        self.assertEqual(signed_url.await_args.args[1].hex, self.user_id.replace("-", ""))
        self.assertEqual(delete_file.await_args.args[1].hex, self.user_id.replace("-", ""))

    def test_upload_without_authentication_is_rejected(self):
        self.app.dependency_overrides.clear()
        response = self.client.get(
            "/archivos",
            params={"tipo_entidad": "lote", "id_entidad": str(uuid4())},
        )
        self.assertEqual(response.status_code, 401)


class StorageValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_document_rejects_image_type(self):
        with self.assertRaises(HTTPException) as raised:
            await storage_service.upload_file(
                entity_type="proyecto",
                entity_id=uuid4(),
                category="project_document",
                original_name="foto.png",
                content_type="image/png",
                data=b"\x89PNG\r\n\x1a\ncontenido",
                user={"id": str(uuid4())},
                access_token="test-token",
            )
        self.assertEqual(raised.exception.status_code, 415)

    async def test_file_signature_must_match_declared_type(self):
        with self.assertRaises(HTTPException) as raised:
            await storage_service.upload_file(
                entity_type="proyecto",
                entity_id=uuid4(),
                category="project_document",
                original_name="falso.pdf",
                content_type="application/pdf",
                data=b"not a PDF",
                user={"id": str(uuid4())},
                access_token="test-token",
            )
        self.assertEqual(raised.exception.status_code, 415)


if __name__ == "__main__":
    unittest.main()
