#!/usr/bin/env python3
"""Minimal Nexus Dashboard REST client for lab provisioning (cookie auth, self-signed certs).

Credentials come from the environment only (source env_prod/env.sh on the lab host):
ND_IP4, ND_USERNAME, ND_PASSWORD, ND_DOMAIN (default DefaultAuth).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(frozen=True)
class NDCredentials:
    """Where and how to log in."""

    ip: str
    username: str
    password: str
    domain: str = "DefaultAuth"

    @classmethod
    def from_env(cls, ip: Optional[str] = None) -> "NDCredentials":
        env = os.environ
        try:
            return cls(ip=ip or env["ND_IP4"], username=env["ND_USERNAME"], password=env["ND_PASSWORD"], domain=env.get("ND_DOMAIN", "DefaultAuth"))
        except KeyError as exc:
            raise SystemExit(f"missing environment variable {exc}; source env_prod/env.sh first") from exc


class NDClient:
    """Thin wrapper around requests.Session for /api/v1/manage."""

    BASE = "/api/v1/manage"

    def __init__(self, creds: NDCredentials, timeout: int = 60) -> None:
        self.creds = creds
        self.timeout = timeout
        self.url = f"https://{creds.ip}"
        self.session = requests.Session()
        self.session.verify = False

    def login(self) -> None:
        body = {"userName": self.creds.username, "userPasswd": self.creds.password, "domain": self.creds.domain}
        resp = self.session.post(f"{self.url}/login", json=body, timeout=self.timeout)
        if resp.status_code != 200:
            raise SystemExit(f"ND login to {self.creds.ip} failed: HTTP {resp.status_code} {resp.text[:200]}")
        content_type = resp.headers.get("Content-Type", "")
        try:
            parsed = resp.json() if resp.content else None
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict):
            raise SystemExit(f"ND login to {self.creds.ip} answered HTTP 200 but not JSON ({content_type}) -- the API is not ready (node still bootstrapping?)")

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self.url}{self.BASE}{path}"
        kwargs.setdefault("timeout", self.timeout)
        return self.session.request(method, url, **kwargs)

    def _json(self, resp: requests.Response, path: str) -> Any:
        method = resp.request.method
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            content_type = resp.headers.get("Content-Type", "")
            raise RuntimeError(
                f"{method} {path} -> HTTP {resp.status_code} returned non-JSON ({content_type}); is the ND API up? body starts: {resp.text[:120]!r}"
            ) from None

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._json(self.request("GET", path, params=params), path)

    def post(self, path: str, json: Any = None, timeout: Optional[int] = None) -> Any:
        """POST; `timeout` overrides the session default for long synchronous actions (configSave, deploy)."""
        kwargs: dict[str, Any] = {"json": json}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self._json(self.request("POST", path, **kwargs), path)

    def put(self, path: str, json: Any) -> Any:
        return self._json(self.request("PUT", path, json=json), path)

    def delete(self, path: str) -> Any:
        return self._json(self.request("DELETE", path), path)

    def paged(self, path: str, key: str, params: Optional[dict] = None, page: int = 100) -> list[dict]:
        """Walk offset/max pagination. ND silently pages some lists (policies) at 10; never trust one read."""
        items: list[dict] = []
        offset = 0
        while True:
            query = dict(params or {}, offset=offset, max=page)
            body = self.get(path, params=query) or {}
            chunk = body.get(key, []) if isinstance(body, dict) else body
            if not chunk:
                return items
            items.extend(chunk)
            offset += len(chunk)
            total = (body.get("meta", {}).get("counts", {}) or {}).get("total") if isinstance(body, dict) else None
            if total is not None and len(items) >= total:
                return items
