import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests


class OutlookMailClient:
    def __init__(self, base_url, api_key, category_key="mregister", tag_key="chatgpt_registered", timeout=30):
        self.base_url = base_url.rstrip("/")
        self.category_key = str(category_key or "mregister").strip().lower()
        self.tag_key = str(tag_key or "chatgpt_registered").strip().lower()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "mregister-outlook-worker",
        })
        self._mailbox_snapshots = {}

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()

    def ensure_classifications(self):
        payload = self._request("GET", "/classifications")
        categories = payload.get("categories", []) if isinstance(payload, dict) else []
        tags = payload.get("tags", []) if isinstance(payload, dict) else []
        has_category = any(str(item.get("key", "")).strip().lower() == self.category_key for item in categories if isinstance(item, dict))
        has_tag = any(str(item.get("key", "")).strip().lower() == self.tag_key for item in tags if isinstance(item, dict))

        if not has_category:
            self._request("POST", "/classifications/categories", json={"name_zh": "MREGISTER", "name_en": self.category_key})
        if not has_tag:
            self._request("POST", "/classifications/tags", json={"name_zh": "已注册 ChatGPT", "name_en": self.tag_key})

    def acquire_account(self):
        self.ensure_classifications()
        page = 1
        while page <= 20:
            payload = self._request(
                "GET",
                f"/accounts?page={page}&page_size=100&category_key={self.category_key}",
            )
            accounts = payload.get("accounts", []) if isinstance(payload, dict) else []
            for account in accounts:
                email = str(account.get("email_id", "")).strip().lower()
                tag_keys = [str(item).strip().lower() for item in (account.get("tag_keys") or [])]
                if email and self.tag_key not in tag_keys:
                    self._mailbox_snapshots[email] = self._current_top_message_id(email)
                    return {
                        "email": email,
                        "tag_keys": tag_keys,
                        "category_key": str(account.get("category_key", "")).strip().lower() or self.category_key,
                    }
            if page >= int(payload.get("total_pages") or 1):
                break
            page += 1
        raise RuntimeError(f"未找到分类 {self.category_key} 下未打 {self.tag_key} 标签的邮箱")

    def create_temp_email(self):
        account = self.acquire_account()
        return account["email"], account

    def _current_top_message_id(self, email):
        payload = self._request("GET", f"/emails/{quote(email, safe='')}?folder=inbox&page=1&page_size=1&refresh=true")
        items = payload.get("emails", []) if isinstance(payload, dict) else []
        if not items:
            return None
        return str(items[0].get("message_id") or "").strip() or None

    def _parse_message_date(self, raw_value):
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except Exception:
            return None

    def extract_verification_code(self, content):
        if not content:
            return None
        patterns = [
            r"Verification code:?\s*(\d{6})",
            r"code is\s*(\d{6})",
            r"验证码[:：]?\s*(\d{6})",
            r"(?<![#&])\b(\d{6})\b",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                return matches[0]
        return None

    def wait_for_verification_code(self, email, timeout=60, exclude_codes=None):
        exclude_codes = exclude_codes or set()
        started_at = datetime.now(timezone.utc)
        previous_top = self._mailbox_snapshots.get(email)
        deadline = time.time() + timeout
        while time.time() < deadline:
            payload = self._request("GET", f"/emails/{quote(email, safe='')}?folder=inbox&page=1&page_size=5&refresh=true")
            emails = payload.get("emails", []) if isinstance(payload, dict) else []
            if emails:
                top_message_id = str(emails[0].get("message_id") or "").strip()
                if top_message_id and top_message_id != previous_top:
                    detail = self._request("GET", f"/emails/{quote(email, safe='')}/{quote(top_message_id, safe='')}")
                    message_date = self._parse_message_date(detail.get("date"))
                    if message_date is None or message_date >= started_at:
                        content = "\n".join(
                            str(part or "")
                            for part in [detail.get("subject"), detail.get("body_plain"), detail.get("body_html")]
                        )
                        code = self.extract_verification_code(content)
                        if code and code not in exclude_codes:
                            self._mailbox_snapshots[email] = top_message_id
                            return code
            time.sleep(2)
        return None

    def mark_registered(self, email, existing_tags=None):
        tag_keys = [str(item).strip().lower() for item in (existing_tags or [])]
        if self.tag_key not in tag_keys:
            tag_keys.append(self.tag_key)
        self._request(
            "PUT",
            f"/accounts/{quote(email, safe='')}/classification",
            json={"category_key": self.category_key, "tag_keys": tag_keys},
        )
