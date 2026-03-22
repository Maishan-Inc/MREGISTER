"""
GPTMail API client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class GPTMailAPIError(RuntimeError):
    status_code: int | None
    message: str
    response: Any | None = None
    url: str | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"(status={self.status_code})")
        if self.url:
            parts.append(f"url={self.url}")
        return " ".join(parts)


class GPTMailClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "chatgpt-register-v2/gptmail-client",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if not path.startswith("/"):
            path = "/" + path

        url = f"{self.base_url}{path}"
        try:
            response = self._session.request(method, url, params=params, json=json_body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise GPTMailAPIError(None, f"Request failed: {exc}", url=url) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GPTMailAPIError(response.status_code, "Non-JSON response", response=response.text, url=url) from exc

        if isinstance(payload, dict) and payload.get("success") is True:
            return payload.get("data")

        message = "API request failed"
        if isinstance(payload, dict) and payload.get("error"):
            message = str(payload["error"])
        raise GPTMailAPIError(response.status_code, message, response=payload, url=url)

    def generate_email(self, *, prefix: str | None = None, domain: str | None = None) -> str:
        if prefix or domain:
            data = self._request("POST", "/api/generate-email", json_body={"prefix": prefix, "domain": domain})
        else:
            data = self._request("GET", "/api/generate-email")

        if not isinstance(data, dict) or not data.get("email"):
            raise GPTMailAPIError(None, "Malformed generate-email response", response=data)
        return str(data["email"])

    def list_emails(self, email: str) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/emails", params={"email": email})
        if not isinstance(data, dict):
            raise GPTMailAPIError(None, "Malformed emails response", response=data)
        emails = data.get("emails", [])
        if not isinstance(emails, list):
            raise GPTMailAPIError(None, "Malformed emails list", response=data)
        return [item for item in emails if isinstance(item, dict)]

    def get_email(self, email_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/api/email/{email_id}")
        if not isinstance(data, dict):
            raise GPTMailAPIError(None, "Malformed email detail response", response=data)
        return data


def iter_strings(obj: Any) -> list[str]:
    out: list[str] = []

    def _walk(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if value:
                out.append(value)
            return
        if isinstance(value, bytes):
            try:
                text = value.decode("utf-8", errors="replace")
            except Exception:
                return
            if text:
                out.append(text)
            return
        if isinstance(value, dict):
            for child in value.values():
                _walk(child)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                _walk(child)

    _walk(obj)
    return out


def extract_email_id(summary: dict[str, Any]) -> str | None:
    for key in ("id", "_id", "email_id", "emailId", "message_id", "messageId", "mail_id", "mailId"):
        value = summary.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
