import importlib.util
import json
import shlex
import subprocess
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MODULE_PATH = Path(__file__).resolve().parents[1] / "web_ui.py"
spec = importlib.util.spec_from_file_location("web_ui", MODULE_PATH)
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.portal = web.Portal("localhost", 9015)

    def test_validate_connection(self):
        for host in ("http://example.com", "host/path", "host:80", "-bad", "", "a b"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                web.Portal(host, 9015)
        for port in (0, 65536, True, "text"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                web.Portal("localhost", port)
        self.assertEqual(web.Portal("::1", 9015).endpoint, "http://[::1]:9015")

    def test_entities_use_working_legacy_tree_endpoint(self):
        data = {"catEntities": {"children": [
            {"id": 7, "name": "one"}, {"id": 8, "name": "two"}
        ]}}
        with patch.object(self.portal, "request", return_value=data) as request:
            self.assertEqual(self.portal.entities(), [{"id": 7, "name": "one"}, {"id": 8, "name": "two"}])
            request.assert_called_once_with("GET", "/netwin/nacatalogs/entities-tree/6")

    def test_invalid_entity_tree_is_not_treated_as_empty(self):
        for data in ({}, {"catEntities": {}}, {"catEntities": {"children": "invalid"}},
                     {"catEntities": {"children": [{"name": "missing ID"}]}}):
            with self.subTest(data=data), patch.object(self.portal, "request", return_value=data):
                with self.assertRaises((ValueError, web.PortalError)):
                    self.portal.entities()

    def test_unknown_entity_does_not_fetch_entries(self):
        with patch.object(self.portal, "request", return_value={"catEntities": {"children": []}}) as request:
            with self.assertRaisesRegex(ValueError, "Entity not found"):
                self.portal.entries("missing")
            self.assertEqual(request.call_count, 1)

    def test_entries_filter_uses_discovered_id(self):
        with patch.object(self.portal, "entity", return_value={"id": 42, "name": "catalog"}), \
                patch.object(self.portal, "request", return_value={"nacatalogs": [{"id": 9}]}) as request:
            self.assertEqual(self.portal.entries("catalog"), [{"id": 9}])
            self.assertIn("idCatEntity+eq+42", request.call_args.args[1])

    def test_invalid_entry_response_is_error(self):
        with patch.object(self.portal, "entity", return_value={"id": 42}), \
                patch.object(self.portal, "request", return_value={"nacatalogs": "invalid"}):
            with self.assertRaises(web.PortalError):
                self.portal.entries("catalog")

    def test_connectivity_check_uses_tcp_connection(self):
        with patch.object(web.socket, "create_connection") as create_connection:
            self.assertTrue(self.portal.connectivity_check())
            create_connection.assert_called_once_with(("localhost", 9015), timeout=5)

    def test_connectivity_check_returns_false_when_connection_fails(self):
        with patch.object(web.socket, "create_connection", side_effect=OSError("connection refused")):
            self.assertFalse(self.portal.connectivity_check())


class DispatchTests(unittest.TestCase):
    def call(self, action, **kwargs):
        return web.dispatch({"host": "localhost", "port": 9015, "action": action,
                             "entity": "catalog", **kwargs})

    def test_mutations_require_confirmation(self):
        for action in ("insert_entity", "delete_entity", "delete_entries", "insert_entries"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "Confirm"):
                self.call(action)

    def test_documented_api_operations_are_loaded(self):
        self.assertEqual(len(web.API_OPERATIONS), 47)
        self.assertEqual(len(web.OPERATIONS_BY_ID), 47)
        self.assertIn("GET /health", web.OPERATIONS_BY_ID)
        self.assertIn("GET /netwin/catalog/entities-full/{idCatEntity}", web.OPERATIONS_BY_ID)
        self.assertNotIn("GET /netwin/na/catalog/entities-full/{idCatEntity}", web.OPERATIONS_BY_ID)

    def test_api_examples_are_available_for_path_query_and_body(self):
        operation = web.OPERATIONS_BY_ID["GET /netwin/nacatalogs/{id}"]
        self.assertEqual(operation["parameters"][0]["name"], "id")
        self.assertEqual(operation["parameters"][0]["example"], "14472")
        operation = web.OPERATIONS_BY_ID[
            "GET /na-portal-go-rest-interface/restful/naportal/go/templates"]
        self.assertEqual(next(p["example"] for p in operation["parameters"] if p["name"] == "$id"), "6")
        operation = web.OPERATIONS_BY_ID[
            "POST /na-portal-mpt-rest-interface/restful/naportal/nodes"]
        self.assertTrue(operation["body"]["schemaDerived"])
        self.assertEqual(operation["body"]["example"][0]["password"], "REPLACE_ME")

    def test_required_api_body_cannot_be_omitted(self):
        with patch.object(web, "Portal") as cls:
            with self.assertRaisesRegex(ValueError, "requires a JSON request body"):
                self.call("api_request", operation="POST /netwin/nacatalogs", confirm=True)
            cls.return_value.request.assert_not_called()

    def test_connectivity_check_only_probes_tcp(self):
        with patch.object(web, "Portal") as cls:
            cls.return_value.port = 9015
            cls.return_value.connectivity_check.return_value = True
            result = self.call("connectivity_check")
            cls.return_value.connectivity_check.assert_called_once_with()
            cls.return_value.request.assert_not_called()
            self.assertEqual(result["response"], {"reachable": True})
            self.assertEqual(result["message"], "Connectivity check: port 9015 is open.")

    def test_health_check_propagates_backend_error(self):
        with patch.object(web, "Portal") as cls:
            cls.return_value.request.side_effect = web.PortalError("Portal returned HTTP 500")
            with self.assertRaisesRegex(web.PortalError, "HTTP 500"):
                self.call("health_check")
            cls.return_value.request.assert_called_once_with("GET", "/health", allow_empty=True)
            cls.return_value.connectivity_check.assert_not_called()

    def test_documented_api_request_resolves_path_and_query_parameters(self):
        with patch.object(web, "Portal") as cls:
            cls.return_value.request.return_value = {"ok": True}
            result = self.call(
                "api_request",
                operation="GET /na-portal-mpt-rest-interface/restful/naportal/mpt/operations/{id}/hdrs",
                path_params={"id": "a/b ?"},
                query={"$select": ["name", "state"], "enabled": True},
            )
            cls.return_value.request.assert_called_once_with(
                "GET",
                "/na-portal-mpt-rest-interface/restful/naportal/mpt/operations/a%2Fb%20%3F/hdrs"
                "?%24select=name&%24select=state&enabled=true",
                None,
            )
            self.assertEqual(result["response"], {"ok": True})

    def test_documented_api_request_rejects_unlisted_route(self):
        with patch.object(web, "Portal") as cls:
            with self.assertRaisesRegex(ValueError, "published API list"):
                self.call("api_request", operation="GET /anything", path_params={}, query={})
            cls.return_value.request.assert_not_called()

    def test_documented_api_mutation_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            self.call("api_request", operation="POST /netwin/nacatalogs", path_params={}, query={})

    def test_documented_api_request_rejects_missing_path_parameters(self):
        with self.assertRaisesRegex(ValueError, "exactly the path parameters"):
            self.call(
                "api_request",
                operation="GET /netwin/nacatalogs/{id}",
                path_params={},
                query={},
            )

    def test_insert_entries_sets_entity_and_strips_id(self):
        with patch.object(web, "Portal") as cls:
            portal = cls.return_value
            portal.entity.return_value = {"id": 7}
            result = self.call("insert_entries", confirm=True,
                               payload={"nacatalogs": [{"id": 99, "idCatEntity": -1, "name": "entry"}]})
            portal.request.assert_called_once_with("POST", "/netwin/nacatalogs",
                                                   {"idCatEntity": 7, "name": "entry"})
            self.assertEqual(result["message"], "1 entries inserted.")

    def test_insert_rejects_invalid_batch_before_any_post(self):
        with patch.object(web, "Portal") as cls:
            for payload in ([], [None], [{"name": "valid"}, {}], "text"):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    self.call("insert_entries", confirm=True, payload=payload)
            cls.return_value.request.assert_not_called()

    def test_partial_insert_reports_progress(self):
        with patch.object(web, "Portal") as cls:
            cls.return_value.entity.return_value = {"id": 7}
            cls.return_value.request.side_effect = [None, web.PortalError("HTTP 500")]
            with self.assertRaisesRegex(web.PortalError, "1 entries inserted before failure"):
                self.call("insert_entries", confirm=True, payload=[{"name": "a"}, {"name": "b"}])

    def test_delete_uses_documented_entity_scoped_endpoint(self):
        with patch.object(web, "Portal") as cls:
            cls.return_value.entity.return_value = {"id": 42}
            result = self.call("delete_entries", confirm=True)
            self.assertEqual(result["message"], "All entries deleted from catalog.")
            cls.return_value.request.assert_called_once_with("DELETE", "/netwin/na/catalog/42")
            cls.return_value.entries.assert_not_called()

    def test_entity_delete_escapes_name(self):
        with patch.object(web, "Portal") as cls:
            self.call("delete_entity", entity="a/b", confirm=True)
            cls.return_value.request.assert_called_once_with("DELETE", "/netwin/catalog-entities/a%2Fb")

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        cls.server.token = "test-token"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_assets_and_session(self):
        for path in ("/", "/app.js", "/style.css"):
            with self.subTest(path=path), urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        with urlopen(self.url + "/api/session") as response:
            self.assertEqual(json.load(response)["token"], "test-token")
        with urlopen(self.url + "/api/operations") as response:
            self.assertEqual(len(json.load(response)), 47)

    def test_bad_host_rejected(self):
        request = Request(self.url, headers={"Host": "untrusted.example"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_no_path_traversal(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/../web_ui.py")
        self.assertEqual(error.exception.code, 404)

    def post(self, data, **headers):
        request = Request(self.url + "/api/action", data=json.dumps(data).encode(),
                          headers={"Content-Type": "application/json", **headers}, method="POST")
        return urlopen(request)

    def test_missing_token_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.post({})
        self.assertEqual(error.exception.code, 403)

    def test_cross_origin_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.post({}, **{"X-Portal-Token": "test-token", "Origin": "http://untrusted.example"})
        self.assertEqual(error.exception.code, 403)

    def test_invalid_body_is_client_error(self):
        with self.assertRaises(HTTPError) as error:
            self.post([], **{"X-Portal-Token": "test-token"})
        self.assertEqual(error.exception.code, 400)

    def test_action_success_and_upstream_error(self):
        with patch.object(web, "dispatch", return_value={"entities": []}):
            with self.post({}, **{"X-Portal-Token": "test-token"}) as response:
                self.assertEqual(json.load(response), {"entities": [], "calls": []})
        with patch.object(web, "dispatch", side_effect=web.PortalError("upstream failed")):
            with self.assertRaises(HTTPError) as error:
                self.post({}, **{"X-Portal-Token": "test-token"})
            self.assertEqual(error.exception.code, 502)
            self.assertEqual(json.load(error.exception), {"error": "upstream failed", "calls": []})


class TraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class FakePortal(web.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    return
                if self.path.startswith("/headers"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "accept": self.headers.get("Accept"),
                        "content_type": self.headers.get("Content-Type"),
                    }).encode())
                    return
                if self.path == "/download":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.end_headers()
                    self.wfile.write(b"\x00\xff")
                    return
                self.send_response(503 if self.path == "/failure" else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"message": "raw response"}\n')

            def do_POST(self):
                self.send_response(201)
                self.end_headers()
                self.wfile.write(self.rfile.read(int(self.headers["Content-Length"])))

        cls.server = web.ThreadingHTTPServer(("127.0.0.1", 0), FakePortal)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.trace = []
        self.portal = web.Portal("127.0.0.1", self.server.server_port, trace=self.trace)

    def test_get_records_exact_response_and_status(self):
        self.portal.request("GET", "/test?%24filter=name+eq+%27catalog%27")
        call = self.trace[0]
        self.assertEqual(call["status"], 200)
        self.assertEqual(call["response"], '{"message": "raw response"}\n')
        self.assertIsInstance(call["duration_ms"], int)
        self.assertIn(self.portal.endpoint, call["curl"])
        self.assertEqual(call["error"], None)

    def test_api_explorer_accepts_documented_empty_health_response(self):
        result = web.dispatch({"host": self.portal.host, "port": self.portal.port,
                               "action": "api_request", "operation": "GET /health"})
        self.assertIsNone(result["response"])
        with self.assertRaisesRegex(web.PortalError, "empty response"):
            self.portal.request("GET", "/health")

    def test_health_page_accepts_empty_successful_response(self):
        result = web.dispatch({"host": self.portal.host, "port": self.portal.port,
                               "action": "health_check"}, trace=self.trace)
        self.assertEqual(result, {"message": "Backend health check passed.", "response": None})
        self.assertEqual(self.trace[0]["status"], 200)

    def test_curl_replays_post_payload_with_shell_metacharacters(self):
        payload = {"name": "O'Brien $(touch /not-executed) ${HOME} `id` \u00a7"}
        self.assertEqual(self.portal.request("POST", "/test", payload), payload)
        call = self.trace[0]
        args = shlex.split(call["curl"])
        self.assertEqual(json.loads(args[args.index("--data-raw") + 1]), payload)
        result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(result.stdout), payload)

    def test_get_and_curl_use_curl_default_accept_without_content_type(self):
        response = self.portal.request("GET", "/headers?%24filter=name+eq+%27catalog%27")
        self.assertEqual(response, {"accept": "*/*", "content_type": None})
        args = shlex.split(self.trace[0]["curl"])
        self.assertEqual(args, ["curl", self.portal.endpoint + "/headers?%24filter=name+eq+%27catalog%27"])
        result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(result.stdout), response)

    def test_http_failure_preserves_raw_body(self):
        with self.assertRaises(web.PortalError):
            self.portal.request("GET", "/failure")
        self.assertEqual(self.trace[0]["status"], 503)
        self.assertEqual(self.trace[0]["response"], '{"message": "raw response"}\n')
        self.assertIn("503", self.trace[0]["error"])

    def test_binary_get_response_is_available_for_download(self):
        response = self.portal.request("GET", "/download")
        self.assertEqual(response, {
            "_download": {"content_type": "application/octet-stream", "data": "AP8="}
        })

    def test_network_failure_is_traced(self):
        with patch.object(self.portal.opener, "open", side_effect=OSError("connection refused")):
            with self.assertRaises(web.PortalError):
                self.portal.request("GET", "/test")
        self.assertIsNone(self.trace[0]["status"])
        self.assertIn("connection refused", self.trace[0]["error"])

    def test_trace_is_per_operation(self):
        self.portal.request("GET", "/test")
        other = web.Portal("127.0.0.1", self.server.server_port)
        self.assertEqual(other.trace, [])


if __name__ == "__main__":
    unittest.main()
