import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Models.schemas import LoteOnboardingCreate, PredioOnboardingCreate
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
                    "ubicacion": {"lat": 4.4, "lng": -75.2},
                    "primer_lote": {
                        "nombre": "Lote inicial",
                        "area_ha": 5,
                        "ubicacion": {"lat": 4.41, "lng": -75.21},
                        "geom": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-75.22, 4.40],
                                [-75.20, 4.40],
                                [-75.20, 4.42],
                                [-75.22, 4.40],
                            ]],
                        },
                    },
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), expected)
        create_predio.assert_called_once()
        self.assertEqual(create_predio.call_args.args[1], self.user)
        body = create_predio.call_args.args[0]
        self.assertEqual(body.ubicacion.lat, 4.4)
        self.assertEqual(body.ubicacion.lng, -75.2)
        self.assertEqual(body.primer_lote.geom.coordinates[0][0], (-75.22, 4.4))

    def test_create_predio_rejects_unclosed_lote_polygon(self):
        with patch.object(onboarding_service, "create_predio") as create_predio:
            response = self.client.post(
                "/predios",
                json={
                    "nombre": "Finca",
                    "municipio": "Ibagué",
                    "departamento": "Tolima",
                    "area_ha": 10,
                    "primer_lote": {
                        "nombre": "Lote inicial",
                        "area_ha": 5,
                        "geom": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-75.22, 4.40],
                                [-75.20, 4.40],
                                [-75.20, 4.42],
                                [-75.22, 4.41],
                            ]],
                        },
                    },
                },
            )

        self.assertEqual(response.status_code, 422)
        create_predio.assert_not_called()

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
        expected_lote = {
            "id": str(uuid4()),
            "nombre": "Lote 1",
            "predio_ubicacion": {"type": "Point", "coordinates": [-75.2, 4.4]},
            "ubicacion": {"type": "Point", "coordinates": [-75.21, 4.41]},
            "geom": {
                "type": "Polygon",
                "coordinates": [[[-75.22, 4.4], [-75.2, 4.4], [-75.2, 4.42], [-75.22, 4.4]]],
            },
        }
        cursor.fetchall.return_value = [expected_lote]
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch.object(onboarding_service, "get_connection", return_value=connection):
            result = onboarding_service.list_lotes({"id": user_id})

        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE cm.perfil_id = %s", query)
        self.assertEqual(parameters, (user_id,))
        self.assertEqual(result, {"lotes": [expected_lote]})
        self.assertIn("ST_AsGeoJSON(p.ubicacion)", query)
        self.assertIn("ST_AsGeoJSON(l.ubicacion)", query)
        self.assertIn("ST_AsGeoJSON(l.geom)", query)
        connection.close.assert_called_once()

    def test_create_predio_persists_geojson_in_same_transaction(self):
        user_id = uuid4()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"id": uuid4()},
            {"id": uuid4()},
            {
                "id": uuid4(),
                "nombre": "Finca",
                "municipio": "Ibagué",
                "departamento": "Tolima",
                "ubicacion": {"type": "Point", "coordinates": [-75.2, 4.4]},
            },
            {
                "id": uuid4(),
                "predio_id": uuid4(),
                "nombre": "Lote inicial",
                "area_ha": 5.0,
                "ubicacion": {"type": "Point", "coordinates": [-75.21, 4.41]},
                "geom": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-75.22, 4.4],
                        [-75.2, 4.4],
                        [-75.2, 4.42],
                        [-75.22, 4.4],
                    ]],
                },
            },
        ]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        body = PredioOnboardingCreate.model_validate(
            {
                "nombre": "Finca",
                "municipio": "Ibagué",
                "departamento": "Tolima",
                "area_ha": "10.00",
                "ubicacion": {"lat": 4.4, "lng": -75.2},
                "primer_lote": {
                    "nombre": "Lote inicial",
                    "area_ha": "5.00",
                    "ubicacion": {"lat": 4.41, "lng": -75.21},
                    "geom": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-75.22, 4.40],
                            [-75.20, 4.40],
                            [-75.20, 4.42],
                            [-75.22, 4.40],
                        ]],
                    },
                },
            }
        )

        with patch.object(onboarding_service, "get_connection", return_value=connection):
            result = onboarding_service.create_predio(body, {"id": str(user_id)})

        self.assertEqual(
            result["predio"]["ubicacion"],
            {"type": "Point", "coordinates": [-75.2, 4.4]},
        )
        self.assertEqual(
            result["lote"]["ubicacion"],
            {"type": "Point", "coordinates": [-75.21, 4.41]},
        )
        self.assertEqual(result["lote"]["geom"]["type"], "Polygon")

        predio_insert = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO predios" in call.args[0]
        )
        self.assertIn("extensions.ST_MakePoint", predio_insert.args[0])
        self.assertEqual(predio_insert.args[1][5:8], (-75.2, -75.2, 4.4))

        lote_insert = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO lotes" in call.args[0]
        )
        self.assertIn("extensions.ST_GeomFromGeoJSON", lote_insert.args[0])
        self.assertEqual(lote_insert.args[1][4:7], (-75.21, -75.21, 4.41))
        self.assertEqual(
            json.loads(lote_insert.args[1][7])["coordinates"][0][0],
            [-75.22, 4.4],
        )
        connection.commit.assert_called_once()

    def test_create_additional_lote_persists_its_geometry(self):
        predio_id = uuid4()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {
                "id": predio_id,
                "nombre": "Finca",
                "municipio": "Ibagué",
                "departamento": "Tolima",
                "area_ha": 10,
            },
            {"id": uuid4(), "nombre": "Lote 2"},
        ]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        body = LoteOnboardingCreate.model_validate(
            {
                "nombre": "Lote 2",
                "area_ha": "2.00",
                "ubicacion": {"lat": 4.41, "lng": -75.21},
                "geom": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-75.22, 4.40],
                        [-75.20, 4.40],
                        [-75.20, 4.42],
                        [-75.22, 4.40],
                    ]],
                },
            }
        )

        with patch.object(onboarding_service, "get_connection", return_value=connection):
            onboarding_service.create_lote(predio_id, body, {"id": str(uuid4())})

        insert = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO lotes" in call.args[0]
        )
        self.assertIn("extensions.ST_GeomFromGeoJSON", insert.args[0])
        self.assertEqual(insert.args[1][4:7], (-75.21, -75.21, 4.41))
        connection.commit.assert_called_once()

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
