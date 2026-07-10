"""
server.py — REST API for MoMo SMS transactions.

Built with the Python standard library only (http.server + json + base64).
No Flask, no FastAPI — the assignment specifies plain http.server.

Endpoints
---------
    GET    /transactions            list all transactions
    GET    /transactions/{id}       fetch a single transaction
    POST   /transactions            create a new transaction
    PUT    /transactions/{id}       update an existing transaction
    DELETE /transactions/{id}       delete a transaction

Auth
----
All endpoints are protected with HTTP Basic Auth. Credentials are read from
environment variables `API_USERNAME` and `API_PASSWORD`, falling back to
"admin"/"password123" for the demo. Any request without valid credentials
gets 401 Unauthorized.

Running
-------
    python api/server.py                 # listens on :8000
    PORT=9000 python api/server.py       # override port
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Allow running as `python api/server.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dsa.parse_xml import parse_xml   # noqa: E402


# ---------------------------------------------------------------------------
# Configuration.
# ---------------------------------------------------------------------------
REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_PATH    = os.path.join(REPO_ROOT, "data", "raw", "modified_sms_v2.xml")
PORT        = int(os.environ.get("PORT", "8000"))
USERNAME    = os.environ.get("API_USERNAME", "admin")
PASSWORD    = os.environ.get("API_PASSWORD", "password123")


# ---------------------------------------------------------------------------
# In-memory data store.
#
# We load the XML once at startup and keep both a list (for ordered
# iteration on GET /transactions) and a dictionary index (for O(1) lookup
# by id — the same DSA trick benchmarked in dsa/search_comparison.py).
# A lock guards writes so concurrent POST/PUT/DELETE calls stay consistent.
# ---------------------------------------------------------------------------
class TransactionStore:
    def __init__(self, xml_path: str) -> None:
        self._lock = threading.Lock()
        self._transactions: list[dict[str, Any]] = parse_xml(xml_path)
        self._index: dict[int, dict[str, Any]] = {
            t["id"]: t for t in self._transactions
        }
        self._next_id: int = (max(self._index) if self._index else 0) + 1

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._transactions)

    def get(self, tx_id: int) -> dict[str, Any] | None:
        return self._index.get(tx_id)

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            new_id = self._next_id
            self._next_id += 1
            record = {"id": new_id, **payload}
            self._transactions.append(record)
            self._index[new_id] = record
            return record

    def update(self, tx_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            existing = self._index.get(tx_id)
            if existing is None:
                return None
            # Merge — never let the client change the id.
            payload.pop("id", None)
            existing.update(payload)
            return existing

    def delete(self, tx_id: int) -> bool:
        with self._lock:
            existing = self._index.pop(tx_id, None)
            if existing is None:
                return False
            self._transactions.remove(existing)
            return True


STORE = TransactionStore(XML_PATH)


# ---------------------------------------------------------------------------
# Auth helper — validates the incoming Authorization header.
# ---------------------------------------------------------------------------
def credentials_ok(auth_header: str | None) -> bool:
    """Return True if `Authorization: Basic ...` matches configured creds."""
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(auth_header[6:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    if ":" not in raw:
        return False
    user, _, pwd = raw.partition(":")
    return user == USERNAME and pwd == PASSWORD


# ---------------------------------------------------------------------------
# Request handler.
# ---------------------------------------------------------------------------
class TransactionHandler(BaseHTTPRequestHandler):
    # Suppress the default noisy per-request stderr log; we print our own.
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(),
                                         fmt % args))

    # ---------- Response helpers ----------
    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_unauthorized(self) -> None:
        body = json.dumps({"error": "Unauthorized"}).encode("utf-8")
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("WWW-Authenticate", 'Basic realm="MoMo API"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    # ---------- Auth gate ----------
    def _authenticate(self) -> bool:
        if credentials_ok(self.headers.get("Authorization")):
            return True
        self._send_unauthorized()
        return False

    # ---------- Path parsing ----------
    def _match_transactions(self) -> tuple[str, int | None] | None:
        """
        Return ('collection', None) for /transactions,
               ('item', <id>)      for /transactions/<int>,
               None otherwise.
        """
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/transactions":
            return ("collection", None)
        if path.startswith("/transactions/"):
            tail = path[len("/transactions/"):]
            if tail.isdigit():
                return ("item", int(tail))
        return None

    # ---------- HTTP verbs ----------
    def do_GET(self) -> None:                                    # noqa: N802
        if not self._authenticate():
            return

        # Simple root endpoint so a browser visit shows something friendly.
        if self.path in ("/", "/health"):
            self._send_json(HTTPStatus.OK, {
                "service": "MoMo SMS Transactions API",
                "status":  "ok",
                "endpoints": [
                    "GET    /transactions",
                    "GET    /transactions/{id}",
                    "POST   /transactions",
                    "PUT    /transactions/{id}",
                    "DELETE /transactions/{id}",
                ],
            })
            return

        matched = self._match_transactions()
        if matched is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
            return

        kind, tx_id = matched
        if kind == "collection":
            self._send_json(HTTPStatus.OK, STORE.list_all())
            return

        # kind == "item"
        record = STORE.get(tx_id)              # type: ignore[arg-type]
        if record is None:
            self._send_json(HTTPStatus.NOT_FOUND,
                            {"error": f"Transaction {tx_id} not found"})
            return
        self._send_json(HTTPStatus.OK, record)

    def do_POST(self) -> None:                                   # noqa: N802
        if not self._authenticate():
            return
        matched = self._match_transactions()
        if matched is None or matched[0] != "collection":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
            return

        payload = self._read_body_json()
        if payload is None:
            self._send_json(HTTPStatus.BAD_REQUEST,
                            {"error": "Malformed JSON in request body"})
            return
        if not isinstance(payload, dict) or "amount" not in payload:
            self._send_json(HTTPStatus.BAD_REQUEST,
                            {"error": "Body must be a JSON object containing "
                                       "at least an 'amount' field"})
            return

        record = STORE.create(payload)
        self._send_json(HTTPStatus.CREATED, record)

    def do_PUT(self) -> None:                                    # noqa: N802
        if not self._authenticate():
            return
        matched = self._match_transactions()
        if matched is None or matched[0] != "item":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
            return

        _, tx_id = matched
        payload = self._read_body_json()
        if payload is None or not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST,
                            {"error": "Malformed JSON in request body"})
            return

        updated = STORE.update(tx_id, payload)   # type: ignore[arg-type]
        if updated is None:
            self._send_json(HTTPStatus.NOT_FOUND,
                            {"error": f"Transaction {tx_id} not found"})
            return
        self._send_json(HTTPStatus.OK, updated)

    def do_DELETE(self) -> None:                                 # noqa: N802
        if not self._authenticate():
            return
        matched = self._match_transactions()
        if matched is None or matched[0] != "item":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
            return

        _, tx_id = matched
        deleted = STORE.delete(tx_id)            # type: ignore[arg-type]
        if not deleted:
            self._send_json(HTTPStatus.NOT_FOUND,
                            {"error": f"Transaction {tx_id} not found"})
            return
        self._send_json(HTTPStatus.OK,
                        {"deleted": True, "id": tx_id})


# ---------------------------------------------------------------------------
# Entrypoint.
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Loaded {len(STORE.list_all())} transactions from {XML_PATH}")
    print(f"MoMo API listening on http://127.0.0.1:{PORT}")
    print(f"Auth: Basic  (user={USERNAME!r})")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), TransactionHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
