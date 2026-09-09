"""Tests for NDClient.paged() (offset/max pagination) and non-JSON response handling (login/_json)."""

import pytest

from nd_client import NDClient, NDCredentials


def _client() -> NDClient:
    return NDClient(NDCredentials(ip="192.0.2.1", username="admin", password="secret"))


class _FakeRequest:
    """Stand-in for requests.PreparedRequest: NDClient._json only reads .method."""

    def __init__(self, method: str) -> None:
        self.method = method


class _FakeResponse:
    """Minimal stand-in for requests.Response covering the attributes NDClient touches."""

    def __init__(self, status_code: int, text: str, content_type: str = "text/html", method: str = "GET") -> None:
        self.status_code = status_code
        self.text = text
        self.content = text.encode()
        self.headers = {"Content-Type": content_type}
        self.request = _FakeRequest(method)

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class _FakeJsonResponse(_FakeResponse):
    """A 200 response whose body really is JSON."""

    def __init__(self, payload, method: str = "POST") -> None:
        super().__init__(200, '{"ok": true}', content_type="application/json", method=method)
        self._payload = payload

    def json(self):
        return self._payload


def test_paged_follows_total_across_short_pages():
    """Server hard-caps at 10 items per response (as ND does for policies) even though the caller requests
    the default page=100 and meta.counts.total says 25: all 25 must come back, not just the first 10."""
    all_items = [{"n": i} for i in range(25)]
    requested_offsets = []

    def fake_get(path, params=None):
        offset = params["offset"]
        end = offset + 10
        requested_offsets.append(offset)
        chunk = all_items[offset:end]
        return {"things": chunk, "meta": {"counts": {"total": 25}}}

    client = _client()
    client.get = fake_get

    items = client.paged("/things", "things")

    assert items == all_items
    assert requested_offsets == [0, 10, 20]


def test_paged_stops_on_empty_chunk_when_total_unknown():
    """No meta.counts.total: pagination must stop on the first empty chunk, not loop forever."""
    all_items = [{"n": i} for i in range(15)]

    def fake_get(path, params=None):
        offset = params["offset"]
        end = offset + 10
        chunk = all_items[offset:end]
        return {"things": chunk}

    client = _client()
    client.get = fake_get

    items = client.paged("/things", "things", page=10)

    assert items == all_items


def test_json_raises_runtime_error_on_non_json_body():
    """A bootstrapping ND answers every path (including API paths) HTTP 200 with its HTML UI page;
    that must surface as a clear RuntimeError, never an uncaught requests.exceptions.JSONDecodeError."""
    client = _client()
    resp = _FakeResponse(200, "<html><body>Nexus Dashboard</body></html>", method="GET")

    with pytest.raises(RuntimeError, match="non-JSON"):
        client._json(resp, "/fabrics")


def test_login_raises_systemexit_when_200_body_is_not_json(monkeypatch):
    client = _client()
    resp = _FakeResponse(200, "<html><body>Nexus Dashboard</body></html>", method="POST")
    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: resp)

    with pytest.raises(SystemExit, match="not ready"):
        client.login()


def test_login_does_not_raise_when_200_body_is_json_dict(monkeypatch):
    client = _client()
    resp = _FakeJsonResponse({"token": "abc123"}, method="POST")
    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: resp)

    client.login()  # must not raise
