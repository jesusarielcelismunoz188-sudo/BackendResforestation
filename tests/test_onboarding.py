import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Models.schemas import PredioOnboardingCreate
from Routes.auth import require_authenticated_user
from Routes.onboarding import router
from Services import onboarding_service


class OnboardingRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.user = {"id": str(uuid4()), "email": "person@example.com"}
        self.app.include_router(router)
        self.app.dependency_overrides[require_authenticated_user] = lambda: self.user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    def test_list_lotes_uses_authenticated_user(self):
        expected = {"lotes": [{"id": str(uuid4()), "nombre": "Lote 1"}]}
        with patch.object(
            onboarding_service,
            "list_lotes",
            return_value=expected,
        ) as list_lotes:
            response = self.client.get("/lotes")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        list_lotes.assert_called_once_with(self.user)

    def test_create_predio_passes_the_user_from_auth(self):
        expected = {
            "predio": {"id": str(uuid4()), "nombre": "Finca"},
            "lote": {"id": str(uuid4()), "nombre": "Lote inicial"},
        }
        with patch.object(
            onboarding_service,
            "create_predio",
            return_value=expected,
        ) as create_predio:
            response = self.client.post(
                "/predios",
                json={
                    "nombre": "Finca",
                    "municipio": "Ibagué",
                    "departamento": "Tolima",
                    "area_ha": 10,
                    "primer_lote": {"nombre": "Lote inicial", "area_ha": 5},
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), expected)
        create_predio.assert_called_once()
        self.assertEqual(create_predio.call_args.args[1], self.user)

    def test_create_predio_rejects_first_lot_larger_than_predio(self):
        with patch.object(onboarding_service, "create_predio") as create_predio:
            response = self.client.post(
                "/predios",
                json={
                    "nombre": "Finca",
                    "municipio": "Ibagué",
                    "departamento": "Tolima",
                    "area_ha": 2,
                    "primer_lote": {"nombre": "Lote inicial", "area_ha": 5},
                },
            )

        self.assertEqual(response.status_code, 422)
        create_predio.assert_not_called()

    def test_unavailable_lote_projects_return_not_found(self):
        with patch.object(
            onboarding_service,
            "list_proyectos",
            return_value=None,
        ):
            response = self.client.get(f"/lotes/{uuid4()}/proyectos")

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_cannot_access_onboarding(self):
        self.app.dependency_overrides.clear()
        response = self.client.get("/lotes")
        self.assertEqual(response.status_code, 401)


class OnboardingPersistenceTests(unittest.TestCase):
    def test_list_lotes_filters_by_authenticated_user(self):
        user_id = str(uuid4())
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch.object(onboarding_service, "get_connection", return_value=connection):
            result = onboarding_service.list_lotes({"id": user_id})

        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE cm.perfil_id = %s", query)
        self.assertEqual(parameters, (user_id,))
        self.assertEqual(result, {"lotes": []})
        connection.close.assert_called_once()

    def test_create_predio_rolls_back_if_first_lote_insert_fails(self):
        user_id = uuid4()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"id": uuid4()},
            {"id": uuid4()},
            {"id": uuid4(), "nombre": "Finca", "municipio": "Ibagué"},
        ]

        def fail_on_lote_insert(query, _parameters=None):
            if "INSERT INTO lotes" in query:
                raise RuntimeError("database error")

        cursor.execute.side_effect = fail_on_lote_insert
        connection = MagicMock()
        connection.cursor.return_value = cursor
        body = PredioOnboardingCreate.model_validate(
            {
                "nombre": "Finca",
                "municipio": "Ibagué",
                "departamento": "Tolima",
                "area_ha": "10.00",
                "primer_lote": {"nombre": "Lote inicial", "area_ha": "5.00"},
            }
        )

        with (
            patch.object(onboarding_service, "get_connection", return_value=connection),
            self.assertRaises(RuntimeError),
        ):
            onboarding_service.create_predio(body, {"id": str(user_id)})

        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
