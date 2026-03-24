"""
Mail client factory with Skymail, GPTMail, MoeMail, and Cloudflare Temp Email adapters.
"""

from __future__ import annotations

import random
import re
import string
import sys
import time
from email import message_from_string, policy
from urllib.parse import urlencode

import requests

from .gptmail_client import GPTMailAPIError, GPTMailClient, extract_email_id, iter_strings
from .proxy_utils import normalize_proxy_url


def _first_text(*values: object, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _float_value(*values: object, default: float) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _int_value(*values: object, default: int) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def _build_session(proxy: str | None = None) -> requests.Session:
    session = requests.Session()
    normalized_proxy = normalize_proxy_url(proxy)
    if normalized_proxy:
        session.proxies = {"http": normalized_proxy, "https": normalized_proxy}
    return session


def _build_url(base_url: str, path: str, params: dict[str, object] | None = None) -> str:
    clean_base = base_url.rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    url = f"{clean_base}{clean_path}"
    if params:
        filtered = {key: value for key, value in params.items() if value not in (None, "")}
        if filtered:
            url = f"{url}?{urlencode(filtered)}"
    return url


def _generate_local_part(prefix: str | None = None) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    if not prefix:
        return suffix
    normalized = re.sub(r"[^a-z0-9]", "", prefix.lower())
    if not normalized:
        return suffix
    return f"{normalized}{suffix}"


def _decode_email_part(part: object) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
        if isinstance(content, bytes):
            charset = part.get_content_charset() or "utf-8"
            try:
                return content.decode(charset, errors="replace")
            except LookupError:
                return content.decode("utf-8", errors="replace")
    except Exception:
        pass

    try:
        payload = part.get_payload(decode=True)
    except Exception:
        payload = None

    if isinstance(payload, bytes):
        charset = getattr(part, "get_content_charset", lambda: None)() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        return payload
    return ""


def _extract_raw_email_text(raw_email: str) -> tuple[str, str]:
    if not raw_email:
        return "", ""

    try:
        message = message_from_string(raw_email, policy=policy.default)
    except Exception:
        return "", raw_email

    subject = str(message.get("subject") or "")
    parts: list[str] = []

    try:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get_content_disposition() == "attachment":
                    continue
                text = _decode_email_part(part).strip()
                if text:
                    parts.append(text)
        else:
            text = _decode_email_part(message).strip()
            if text:
                parts.append(text)
    except Exception:
        return subject, raw_email

    combined = "\n".join(part for part in parts if part).strip()
    return subject, combined or raw_email


class BaseMailClient:
    """Shared helpers for mail providers."""

    def __init__(self) -> None:
        self._used_codes: set[str] = set()

    @staticmethod
    def extract_verification_code(content: str | None) -> str | None:
        if not content:
            return None

        patterns = [
            r"Verification code:?\s*(\d{6})",
            r"code is\s*(\d{6})",
            r"代码为[:：]?\s*(\d{6})",
            r"验证码[:：]?\s*(\d{6})",
            r">\s*(\d{6})\s*<",
            r"(?<![#&])\b(\d{6})\b",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for code in matches:
                if code == "177010":
                    continue
                return code
        return None

    def wait_for_verification_code(self, email: str, timeout: int = 30, exclude_codes: set[str] | None = None) -> str | None:
        if exclude_codes is None:
            exclude_codes = set()

        all_excluded = exclude_codes | self._used_codes
        seen_message_ids: set[str] = set()

        print(f" ⏳ 等待验证码 (最大 {timeout}s)...")
        start = time.time()
        while time.time() - start < timeout:
            messages = self.fetch_emails(email)
            for item in messages:
                if not isinstance(item, dict):
                    continue

                message_id = str(item.get("emailId") or item.get("id") or "").strip()
                if not message_id or message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)

                candidates = [
                    str(item.get("subject") or ""),
                    str(item.get("content") or ""),
                    str(item.get("text") or ""),
                ]
                for content in candidates:
                    code = self.extract_verification_code(content)
                    if code and code not in all_excluded:
                        print(f" ✅ 验证码: {code}")
                        self._used_codes.add(code)
                        return code

            if time.time() - start < 10:
                time.sleep(0.5)
            else:
                time.sleep(2)

        print(" ⏰ 等待验证码超时")
        return None

    def fetch_emails(self, email: str) -> list[dict[str, str]]:
        """子类需要实现此方法"""
        return []


class SkymailClient(BaseMailClient):
    """Skymail mailbox client."""

    def __init__(self, admin_email: str, admin_password: str, api_base: str | None = None, proxy: str | None = None, domains: list[str] | None = None):
        super().__init__()
        self.admin_email = admin_email
        self.admin_password = admin_password
        if api_base:
            self.api_base = api_base.rstrip("/")
        elif admin_email and "@" in admin_email:
            self.api_base = f"https://{admin_email.split('@')[1]}"
        else:
            self.api_base = ""
        self.proxy = proxy or ""
        self.api_token: str | None = None

        if not domains or not isinstance(domains, list):
            raise Exception("❌ 错误: 未配置 skymail_domains，请在 config.json 中设置域名列表")
        self.domains = [str(item).strip() for item in domains if str(item).strip()]
        if not self.domains:
            raise Exception("❌ 错误: 未配置 skymail_domains，请在 config.json 中设置域名列表")

    def _session(self) -> requests.Session:
        return _build_session(self.proxy or None)

    def generate_token(self) -> str | None:
        if not self.admin_email or not self.admin_password:
            print("⚠️ 未配置 Skymail 管理员账号")
            return None
        if not self.api_base:
            print("⚠️ 无法从管理员邮箱提取 API 域名")
            return None

        try:
            response = self._session().post(
                f"{self.api_base}/api/public/genToken",
                json={"email": self.admin_email, "password": self.admin_password},
                headers={"Content-Type": "application/json"},
                timeout=15,
                verify=False,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    token = data.get("data", {}).get("token")
                    if token:
                        print("✅ 成功生成 Skymail API Token")
                        self.api_token = str(token)
                        return self.api_token
            print(f"⚠️ 生成 Skymail Token 失败: {response.status_code} - {response.text[:200]}")
        except Exception as exc:
            print(f"⚠️ 生成 Skymail Token 异常: {exc}")
        return None

    def create_temp_email(self) -> tuple[str, str]:
        if not self.api_token:
            raise Exception("SKYMAIL_API_TOKEN 未设置，无法创建临时邮箱")

        domain = random.choice(self.domains)
        prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(6, 10)))
        email = f"{prefix}@{domain}"
        return email, email

    def fetch_emails(self, email: str) -> list[dict[str, str]]:
        try:
            response = self._session().post(
                f"{self.api_base}/api/public/emailList",
                json={"toEmail": email, "timeSort": "desc", "num": 1, "size": 20},
                headers={"Authorization": self.api_token or "", "Content-Type": "application/json"},
                timeout=15,
                verify=False,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    return data.get("data", [])
        except Exception:
            return []
        return []


class GPTMailAdapter(BaseMailClient):
    """GPTMail adapter exposing the legacy Skymail-like interface."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        proxy: str | None = None,
        prefix: str | None = None,
        domain: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__()
        session = _build_session(proxy)
        self.client = GPTMailClient(base_url=base_url, api_key=api_key, timeout=timeout, session=session)
        self.api_base = base_url.rstrip("/")
        self.proxy = proxy or ""
        self.prefix = (prefix or "").strip() or None
        self.domain = (domain or "").strip() or None

    def create_temp_email(self) -> tuple[str, str]:
        email = self.client.generate_email(prefix=self.prefix, domain=self.domain)
        return email, email

    def fetch_emails(self, email: str) -> list[dict[str, str]]:
        try:
            summaries = self.client.list_emails(email)
        except GPTMailAPIError:
            return []

        messages: list[dict[str, str]] = []
        for summary in summaries:
            email_id = extract_email_id(summary)
            detail = {}
            if email_id:
                try:
                    detail = self.client.get_email(email_id)
                except GPTMailAPIError:
                    detail = {}

            subject = str(summary.get("subject") or detail.get("subject") or "")
            content_parts = iter_strings(summary) + iter_strings(detail)
            content = "\n".join(part for part in content_parts if part)
            messages.append(
                {
                    "emailId": email_id or "",
                    "subject": subject,
                    "content": content,
                    "text": content,
                }
            )
        return messages


class MoeMailAdapter(BaseMailClient):
    """MoeMail API adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        proxy: str | None = None,
        prefix: str | None = None,
        domain: str | None = None,
        timeout: float = 30.0,
        expiry_time: int = 3600000,
    ) -> None:
        super().__init__()
        self.api_base = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.proxy = proxy or ""
        self.prefix = (prefix or "").strip() or None
        self.domain = (domain or "").strip() or None
        self.timeout = timeout
        self.expiry_time = expiry_time
        self.session = _build_session(proxy)
        self._email_ids: dict[str, str] = {}

    def _request(
        self, method: str, path: str, *, params: dict[str, object] | None = None, json_body: dict[str, object] | None = None
    ) -> dict:
        try:
            response = self.session.request(
                method,
                _build_url(self.api_base, path, params),
                headers={
                    "X-API-Key": self.api_key,
                    "Accept": "application/json",
                    **({"Content-Type": "application/json"} if json_body is not None else {}),
                },
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"MoeMail 请求失败: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"MoeMail 返回了非 JSON 响应: {response.text[:200]}") from exc

        if not response.ok:
            message = payload.get("error") or payload.get("message") or f"HTTP {response.status_code}"
            raise RuntimeError(f"MoeMail 请求失败: {message}")
        return payload

    def _resolve_domain(self) -> str:
        if self.domain:
            return self.domain

        payload = self._request("GET", "/api/config")
        raw_domains = payload.get("emailDomains") or payload.get("domains") or ""
        if isinstance(raw_domains, str):
            candidates = [item.strip() for item in raw_domains.split(",") if item.strip()]
        elif isinstance(raw_domains, list):
            candidates = [str(item).strip() for item in raw_domains if str(item).strip()]
        else:
            candidates = []
        if not candidates:
            raise RuntimeError("MoeMail 未返回可用域名，请在凭据中显式填写域名")
        self.domain = candidates[0]
        return self.domain

    def _resolve_email_id(self, email: str) -> str | None:
        cached = self._email_ids.get(email)
        if cached:
            return cached

        cursor: str | None = None
        for _ in range(20):
            payload = self._request("GET", "/api/emails", params={"cursor": cursor} if cursor else None)
            for item in payload.get("emails", []):
                if not isinstance(item, dict):
                    continue
                address = str(item.get("address") or item.get("email") or "").strip()
                email_id = str(item.get("id") or "").strip()
                if address and email_id:
                    self._email_ids[address] = email_id
                if address == email and email_id:
                    return email_id
            cursor = str(payload.get("nextCursor") or "").strip() or None
            if not cursor:
                break
        return None

    def create_temp_email(self) -> tuple[str, str]:
        payload = {
            "expiryTime": self.expiry_time,
            "domain": self._resolve_domain(),
        }
        local_part = _generate_local_part(self.prefix)
        if local_part:
            payload["name"] = local_part

        data = self._request("POST", "/api/emails/generate", json_body=payload)
        email = str(data.get("email") or data.get("address") or "").strip()
        email_id = str(data.get("id") or "").strip()
        if not email:
            raise RuntimeError("MoeMail 创建邮箱失败: 响应中缺少邮箱地址")
        if email_id:
            self._email_ids[email] = email_id
        return email, email

    def fetch_emails(self, email: str) -> list[dict[str, str]]:
        try:
            email_id = self._resolve_email_id(email)
            if not email_id:
                return []
            payload = self._request("GET", f"/api/emails/{email_id}")
        except RuntimeError:
            return []

        messages: list[dict[str, str]] = []
        for item in payload.get("messages", []):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("html") or "")
            message_id = str(item.get("id") or "").strip()
            messages.append(
                {
                    "id": message_id,
                    "emailId": message_id,
                    "subject": str(item.get("subject") or ""),
                    "content": content,
                    "text": content,
                }
            )
        return messages


class CloudflareTempEmailAdapter(BaseMailClient):
    """Cloudflare Temp Email adapter using admin address creation plus address JWT polling."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        proxy: str | None = None,
        prefix: str | None = None,
        domain: str | None = None,
        secret: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__()
        self.api_base = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.proxy = proxy or ""
        self.prefix = (prefix or "").strip() or None
        self.domain = (domain or "").strip() or None
        self.secret = (secret or "").strip() or None
        self.timeout = timeout
        self.session = _build_session(proxy)
        self._jwt_by_email: dict[str, str] = {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: dict[str, object] | None = None,
        bearer_token: str | None = None,
        use_admin_auth: bool = False,
    ) -> dict:
        headers = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if self.secret:
            headers["X-Custom-Auth"] = self.secret
        if use_admin_auth:
            headers["X-Admin-Auth"] = self.api_key
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        try:
            response = self.session.request(
                method,
                _build_url(self.api_base, path, params),
                headers=headers,
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Cloudflare Temp Email 请求失败: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Cloudflare Temp Email 返回了非 JSON 响应: {response.text[:200]}") from exc

        if not response.ok:
            if isinstance(payload, dict):
                message = payload.get("error") or payload.get("message") or payload.get("detail")
            else:
                message = None
            raise RuntimeError(f"Cloudflare Temp Email 请求失败: {message or response.text[:200] or f'HTTP {response.status_code}'}")
        return payload if isinstance(payload, dict) else {}

    def create_temp_email(self) -> tuple[str, str]:
        body = {
            "name": _generate_local_part(self.prefix),
            "enablePrefix": False,
        }
        if self.domain:
            body["domain"] = self.domain

        data = self._request("POST", "/admin/new_address", json_body=body, use_admin_auth=True)
        email = str(data.get("address") or data.get("email") or "").strip()
        jwt_token = str(data.get("jwt") or "").strip()
        if not email or not jwt_token:
            raise RuntimeError("Cloudflare Temp Email 创建邮箱失败: 响应中缺少地址或 JWT")
        self._jwt_by_email[email] = jwt_token
        return email, email

    def fetch_emails(self, email: str) -> list[dict[str, str]]:
        jwt_token = self._jwt_by_email.get(email)
        if not jwt_token:
            return []

        try:
            payload = self._request(
                "GET",
                "/api/mails",
                params={"limit": 20, "offset": 0},
                bearer_token=jwt_token,
            )
        except RuntimeError:
            return []

        messages: list[dict[str, str]] = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            raw = str(item.get("raw") or "")
            subject, content = _extract_raw_email_text(raw)
            message_id = str(item.get("id") or "").strip()
            messages.append(
                {
                    "id": message_id,
                    "emailId": message_id,
                    "subject": subject,
                    "content": content or raw,
                    "text": content or raw,
                }
            )
        return messages


def init_skymail_client(config: dict) -> BaseMailClient:
    provider = _first_text(config.get("mail_provider"), default="skymail").lower() or "skymail"
    provider = provider.replace("-", "_")

    if provider == "gptmail":
        api_key = _first_text(config.get("mail_api_key"), config.get("gptmail_api_key"))
        base_url = _first_text(
            config.get("mail_base_url"),
            config.get("gptmail_base_url"),
            default="https://mail.chatgpt.org.uk",
        )
        prefix = _first_text(config.get("mail_prefix"), config.get("gptmail_prefix")) or None
        domain = _first_text(config.get("mail_domain"), config.get("gptmail_domain")) or None
        timeout = _float_value(config.get("mail_timeout"), config.get("gptmail_timeout"), default=30.0)
        proxy = _first_text(config.get("proxy")) or None

        if not api_key:
            print("❌ 错误: 未配置 GPTMail API Key")
            print(" 请在 config.json 或环境变量中设置 mail_api_key / MAIL_API_KEY")
            sys.exit(1)

        client = GPTMailAdapter(
            base_url=base_url,
            api_key=api_key,
            proxy=proxy,
            prefix=prefix,
            domain=domain,
            timeout=timeout,
        )
        print(f"📧 使用 GPTMail 邮箱服务: {client.api_base}")
        if domain:
            print(f"📮 指定域名: {domain}")
        if prefix:
            print(f"🪪 指定前缀: {prefix}")
        return client

    if provider == "moemail":
        api_key = _first_text(config.get("mail_api_key"))
        base_url = _first_text(config.get("mail_base_url"))
        prefix = _first_text(config.get("mail_prefix")) or None
        domain = _first_text(config.get("mail_domain")) or None
        timeout = _float_value(config.get("mail_timeout"), default=30.0)
        expiry_time = _int_value(config.get("mail_expiry_time"), default=3600000)
        proxy = _first_text(config.get("proxy")) or None

        if not api_key:
            print("❌ 错误: 未配置 MoeMail API Key")
            print(" 请在 config.json 或环境变量中设置 mail_api_key / MAIL_API_KEY")
            sys.exit(1)
        if not base_url:
            print("❌ 错误: 未配置 MoeMail Base URL")
            print(" 请在 config.json 或环境变量中设置 mail_base_url / MAIL_BASE_URL")
            sys.exit(1)

        client = MoeMailAdapter(
            base_url=base_url,
            api_key=api_key,
            proxy=proxy,
            prefix=prefix,
            domain=domain,
            timeout=timeout,
            expiry_time=expiry_time,
        )
        print(f"📧 使用 MoeMail 邮箱服务: {client.api_base}")
        if domain:
            print(f"📮 指定域名: {domain}")
        if prefix:
            print(f"🪪 地址前缀: {prefix}")
        return client

    if provider == "cloudflare_temp_email":
        api_key = _first_text(config.get("mail_api_key"))
        base_url = _first_text(config.get("mail_base_url"))
        prefix = _first_text(config.get("mail_prefix")) or None
        domain = _first_text(config.get("mail_domain")) or None
        secret = _first_text(config.get("mail_secret")) or None
        timeout = _float_value(config.get("mail_timeout"), default=30.0)
        proxy = _first_text(config.get("proxy")) or None

        if not api_key:
            print("❌ 错误: 未配置 Cloudflare Temp Email 管理密钥")
            print(" 请在 config.json 或环境变量中设置 mail_api_key / MAIL_API_KEY")
            sys.exit(1)
        if not base_url:
            print("❌ 错误: 未配置 Cloudflare Temp Email Base URL")
            print(" 请在 config.json 或环境变量中设置 mail_base_url / MAIL_BASE_URL")
            sys.exit(1)

        client = CloudflareTempEmailAdapter(
            base_url=base_url,
            api_key=api_key,
            proxy=proxy,
            prefix=prefix,
            domain=domain,
            secret=secret,
            timeout=timeout,
        )
        print(f"📧 使用 Cloudflare Temp Email 邮箱服务: {client.api_base}")
        if domain:
            print(f"📮 指定域名: {domain}")
        if prefix:
            print(f"🪪 地址前缀: {prefix}")
        if secret:
            print("🔐 已启用站点访问密码")
        return client

    admin_email = config.get("skymail_admin_email", "")
    admin_password = config.get("skymail_admin_password", "")
    proxy = config.get("proxy", "")
    domains = config.get("skymail_domains", None)

    if not admin_email or not admin_password:
        print("❌ 错误: 未配置 Skymail 管理员账号")
        print(" 请在 config.json 中设置 skymail_admin_email 和 skymail_admin_password")
        sys.exit(1)

    if not domains or not isinstance(domains, list) or len(domains) == 0:
        print("❌ 错误: 未配置 skymail_domains")
        print(' 请在 config.json 中设置域名列表，例如: "skymail_domains": ["admin.example.com"]')
        sys.exit(1)

    client = SkymailClient(admin_email, admin_password, proxy=proxy, domains=domains)
    print(f"🔑 正在生成 Skymail API Token (API: {client.api_base})...")
    print(f"📧 可用域名: {', '.join(client.domains)}")
    token = client.generate_token()
    if not token:
        print("❌ Token 生成失败，无法继续")
        sys.exit(1)
    return client


def init_mail_client(config: dict) -> BaseMailClient:
    return init_skymail_client(config)
