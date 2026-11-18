    #!/usr/bin/env python3
"""Local web interface and documented API Explorer for the NA Portal."""

import argparse
import base64
import hmac
import ipaddress
import json
from pathlib import Path
import re
import secrets
import shlex
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
MAX_BODY = 4 * 1024 * 1024
API_OPERATIONS = json.loads((ROOT / "web" / "api_operations.json").read_text(encoding="utf-8"))
OPERATIONS_BY_ID = {
    "{} {}".format(operation["method"], operation["path"]): operation
    for operation in API_OPERATIONS
}


class PortalError(Exception):
    pass


def object_value(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def records(value, key):
    items = object_value(value).get(key)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise PortalError("Portal response must contain an object array named " + key + ".")
    return items


class Portal:
    def __init__(self, host, port, trace=None):
        if not isinstance(host, str) or not host.strip():
            raise ValueError("Enter a backend hostname or IP address.")
        host = host.strip()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or any(
                not label or len(label) > 63 or not label[0].isalnum()
                or not label[-1].isalnum()
                or not all(c.isascii() and (c.isalnum() or c == "-") for c in label)
                for label in host.split(".")
            ):
                raise ValueError("Use a hostname or IP address, not a URL or path.")
            address = None
        if isinstance(port, bool) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError("Backend port must be between 1 and 65535.")
        self.host = host
        self.port = int(port)
        url_host = "[" + host + "]" if address and address.version == 6 else host
        self.endpoint = "http://{}:{}".format(url_host, self.port)
        self.opener = build_opener(ProxyHandler({}))
        self.trace = trace if trace is not None else []

    def request(self, method, path, payload=None, *, allow_empty=False):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "*/*"}
        if method != "GET" or body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.endpoint + path, data=body, method=method,
                          headers=headers)
        command = ["curl"]
        if method != "GET" or body is not None:
            command.extend(["--request", method, "--header", "Content-Type: application/json"])
        if body is not None:
            command.extend(["--data-raw", body.decode("utf-8")])
        command.append(request.full_url)
        record = {"method": method, "url": request.full_url, "curl": shlex.join(command),
                  "status": None, "response": "", "headers": [], "error": None}
        self.trace.append(record)
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=30) as response:
                record["status"] = response.status
                record["headers"] = list(response.headers.items())
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                record["response"] = text
                content_type = response.headers.get_content_type()
        except HTTPError as exc:
            record["status"] = exc.code
            record["headers"] = list(exc.headers.items())
            record["response"] = exc.read().decode("utf-8", errors="replace")
            record["error"] = "Portal returned HTTP " + str(exc.code)
            exc.close()
            raise PortalError("Portal returned HTTP {}: {}".format(
                exc.code, record["response"][:2000])) from exc
        except (URLError, OSError) as exc:
            record["error"] = str(exc)
            raise PortalError("Cannot reach portal: " + str(exc)) from exc
        finally:
            record["duration_ms"] = round((time.monotonic() - started) * 1000)
        if not text.strip():
            if method == "GET" and not allow_empty:
                raise PortalError("Portal returned an empty response.")
            return None
        try:
            return json.loads(text)
        except ValueError:
            if method == "GET":
                if content_type.startswith("text/") or content_type in (
                    "application/json", "application/xml", "application/javascript",
                ):
                    return text
                return {
                    "_download": {
                        "content_type": content_type,
                        "data": base64.b64encode(raw).decode("ascii"),
                    }
                }
            return text

    def connectivity_check(self):
        try:
            with socket.create_connection((self.host, self.port), timeout=5):
                return True
        except OSError:
            return False

    def entities(self):
        data = object_value(self.request("GET", "/netwin/nacatalogs/entities-tree/6"))
        entities = records(data.get("catEntities"), "children")
        if any("id" not in entity or not isinstance(entity.get("name"), str) for entity in entities):
            raise PortalError("Each catalog entity must have an ID and a name.")
        return [{"id": entity["id"], "name": entity["name"]} for entity in entities]

    def entity(self, name):
        for entity in self.entities():
            if entity["name"] == name:
                return entity
        raise ValueError("Entity not found. Refresh the entity list and select an entity.")

    def entries(self, name):
        entity = self.entity(name)
        query = urlencode({"$filter": "idCatEntity eq " + str(entity["id"])})
        return records(self.request("GET", "/netwin/nacatalogs?" + query), "nacatalogs")

def dispatch(data, trace=None):
    data = object_value(data)
    portal = Portal(data.get("host"), data.get("port"), trace=trace)
    action = data.get("action")
    name = data.get("entity")
    if action in ("delete_entity", "delete_entries", "insert_entity", "insert_entries"):
        if data.get("confirm") is not True:
            raise ValueError("Confirm this operation before continuing.")
    if action in ("entries", "delete_entity", "delete_entries", "insert_entries"):
        if not isinstance(name, str) or not name:
            raise ValueError("Select an entity first.")
    if action == "entities":
        return {"entities": portal.entities()}
    if action == "health_check":
        result = portal.request("GET", "/health", allow_empty=True)
        return {"message": "Backend health check passed.", "response": result}
    if action == "connectivity_check":
        reachable = portal.connectivity_check()
        return {
            "message": "Connectivity check: port {} is {}.".format(
                portal.port, "open" if reachable else "not open"),
            "response": {"reachable": reachable},
        }
    if action == "entries":
        return {"entries": portal.entries(name)}
    if action == "insert_entity":
        payload = object_value(data.get("payload"))
        if not payload:
            raise ValueError("Entity JSON cannot be empty.")
        result = portal.request("POST", "/netwin/catalog-entities", payload)
        return {"message": "Entity definition inserted.", "response": result}
    if action == "delete_entity":
        portal.entity(name)
        result = portal.request("DELETE", "/netwin/catalog-entities/" + quote(name, safe=""))
        return {"message": "Entity deleted.", "response": result}
    if action == "delete_entries":
        entity = portal.entity(name)
        result = portal.request("DELETE", "/netwin/na/catalog/" + quote(str(entity["id"]), safe=""))
        return {"message": "All entries deleted from {}.".format(name), "response": result}
    if action == "insert_entries":
        entity = portal.entity(name)
        payload = data.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("nacatalogs"), list):
            payload = payload["nacatalogs"]
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not payload or not all(isinstance(e, dict) and e for e in payload):
            raise ValueError("Provide an entry object or a non-empty array of entry objects.")
        inserted = 0
        for entry in payload:
            entry = dict(entry)
            entry.pop("id", None)
            entry["idCatEntity"] = entity["id"]
            try:
                portal.request("POST", "/netwin/nacatalogs", entry)
            except PortalError as exc:
                raise PortalError("{} entries inserted before failure. Do not retry the whole batch "
                                  "without checking existing entries. {}".format(inserted, exc)) from exc
            inserted += 1
        return {"message": "{} entries inserted.".format(inserted)}
    if action == "api_request":
        operation_id = data.get("operation")
        if not isinstance(operation_id, str):
            raise ValueError("Choose an operation from the published API list.")
        operation = OPERATIONS_BY_ID.get(operation_id)
        if operation is None:
            raise ValueError("Choose an operation from the published API list.")
        method = operation["method"]
        if method != "GET" and data.get("confirm") is not True:
            raise ValueError("Confirm this operation before continuing.")
        path = operation["path"]
        path_params = data.get("path_params", {})
        if not isinstance(path_params, dict):
            raise ValueError("Path parameters must be a JSON object.")
        placeholders = set(re.findall(r"\{([^{}]+)\}", path))
        if set(path_params) != placeholders:
            raise ValueError("Provide exactly the path parameters shown for this operation.")
        for parameter in placeholders:
            value = path_params[parameter]
            if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value):
                raise ValueError("Path parameter {} must be a non-empty string or integer.".format(parameter))
            path = path.replace("{" + parameter + "}", quote(str(value), safe=""))
        query = data.get("query", {})
        if not isinstance(query, dict):
            raise ValueError("Query parameters must be a JSON object.")
        query_values = []
        for key, value in query.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Query parameter names must be non-empty strings.")
            values = value if isinstance(value, list) else [value]
            if any(not isinstance(item, (str, int, float, bool)) for item in values):
                raise ValueError("Query parameter values must be strings, numbers, booleans, or arrays of these.")
            query_values.extend(
                (key, str(item).lower() if isinstance(item, bool) else str(item))
                for item in values
            )
        if query_values:
            path += "?" + urlencode(query_values)
        payload = data.get("payload")
        if operation.get("body", {}).get("required") and payload is None:
            raise ValueError("This operation requires a JSON request body.")
        options = {"allow_empty": True} if operation.get("allowEmptyResponse") else {}
        result = portal.request(method, path, payload, **options)
        return {
            "message": "{} {} completed.".format(method, operation["path"]),
            "response": result,
        }
    raise ValueError("Unknown menu action.")


class Handler(BaseHTTPRequestHandler):
    def send_content(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, value):
        self.send_content(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

    def valid_host(self):
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit("http://" + host)
            return (
                parsed.hostname in ("localhost", "127.0.0.1", "::1")
                and parsed.port == self.server.server_port
                and parsed.netloc == host
                and parsed.username is None
            )
        except ValueError:
            return False

    def do_GET(self):
        if not self.valid_host():
            self.send_json(403, {"error": "Use the localhost URL printed by the server."})
            return
        path = urlsplit(self.path).path
        if path == "/api/session":
            self.send_json(200, {"token": self.server.token})
            return
        if path == "/api/operations":
            self.send_json(200, API_OPERATIONS)
            return
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path not in files:
            self.send_json(404, {"error": "Not found."})
            return
        filename, content_type = files[path]
        self.send_content(200, (ROOT / "web" / filename).read_bytes(), content_type)

    def do_POST(self):
        if not self.valid_host() or not hmac.compare_digest(
                self.headers.get("X-Portal-Token", ""), self.server.token):
            self.send_json(403, {"error": "Invalid session. Reload the page."})
            return
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers["Host"]:
            self.send_json(403, {"error": "Cross-origin requests are not allowed."})
            return
        if self.path != "/api/action":
            self.send_json(404, {"error": "Not found."})
            return
        trace = []
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("Request body must be between 1 byte and 4 MB.")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Content-Type must be application/json.")
            data = json.loads(self.rfile.read(length))
            result = dispatch(data, trace=trace)
            self.send_json(200, {**result, "calls": trace})
        except (ValueError, UnicodeError) as exc:
            self.send_json(400, {"error": str(exc), "calls": trace})
        except PortalError as exc:
            self.send_json(502, {"error": str(exc), "calls": trace})
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_json(500, {"error": "Unexpected server error. See the server terminal for details.",
                                 "calls": trace})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080, help="Local web UI port (default: 8080)")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.token = secrets.token_urlsafe(32)
    print("NA Portal UI: http://127.0.0.1:{}/".format(server.server_port), flush=True)
    print("Local use only. Mutating API requests require explicit confirmation.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
