"""
Mail client factory with Skymail and GPTMail adapters.
"""

from __future__ import annotations

import random
import re
import string
import sys
import time

import requests

from .gptmail_client import GPTMailAPIError, GPTMailClient, extract_email_id, iter_strings


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

        print(f"  ⏳ 等待验证码 (最大 {timeout}s)...")
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
                        print(f"  ✅ 验证码: {code}")
                        self._used_codes.add(code)
                        return code

            if time.time() - start < 10:
                time.sleep(0.5)
            else:
                time.sleep(2)

        print("  ⏰ 等待验证码超时")
        return None


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
        session = requests.Session()
        if self.proxy:
            session.proxies = {"http": self.proxy, "https": self.proxy}
        return session

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
        session = requests.Session()
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}
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


def init_skymail_client(config: dict) -> BaseMailClient:
    provider = str(config.get("mail_provider", "skymail")).strip().lower() or "skymail"

    if provider == "gptmail":
        api_key = str(config.get("gptmail_api_key", "")).strip()
        base_url = str(config.get("gptmail_base_url", "https://mail.chatgpt.org.uk")).strip() or "https://mail.chatgpt.org.uk"
        prefix = str(config.get("gptmail_prefix", "")).strip() or None
        domain = str(config.get("gptmail_domain", "")).strip() or None
        timeout = float(config.get("gptmail_timeout", 30) or 30)
        proxy = str(config.get("proxy", "")).strip() or None

        if not api_key:
            print("❌ 错误: 未配置 GPTMail API Key")
            print("   请在 config.json 或环境变量中设置 gptmail_api_key / GPTMAIL_API_KEY")
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

    admin_email = config.get("skymail_admin_email", "")
    admin_password = config.get("skymail_admin_password", "")
    proxy = config.get("proxy", "")
    domains = config.get("skymail_domains", None)

    if not admin_email or not admin_password:
        print("❌ 错误: 未配置 Skymail 管理员账号")
        print("   请在 config.json 中设置 skymail_admin_email 和 skymail_admin_password")
        sys.exit(1)

    if not domains or not isinstance(domains, list) or len(domains) == 0:
        print("❌ 错误: 未配置 skymail_domains")
        print('   请在 config.json 中设置域名列表，例如: "skymail_domains": ["admin.example.com"]')
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
