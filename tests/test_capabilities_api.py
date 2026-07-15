import unittest

from fastapi.testclient import TestClient

from app.main import app


class CapabilitiesApiTests(unittest.TestCase):
    def test_capabilities_route_describes_reusable_interfaces(self):
        route_paths = set(app.openapi()["paths"])
        self.assertIn("/api/capabilities", route_paths)

        response = TestClient(app).get("/api/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], "v1.2")
        self.assertTrue(payload["reusable"])
        self.assertFalse(payload["privacy_boundary"]["returns_api_keys"])
        paths = {item["path"] for item in payload["capabilities"]}
        self.assertIn("/api/records/extract-fields", paths)
        self.assertIn("/api/records/build-draft", paths)
        self.assertIn("/api/records/quality", paths)


if __name__ == "__main__":
    unittest.main()
