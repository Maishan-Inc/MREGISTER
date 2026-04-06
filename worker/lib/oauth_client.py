import secrets
import time
from urllib.parse import parse_qs, urlparse

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    import requests as curl_requests

from .sentinel_token import build_sentinel_token
from .utils import generate_datadog_trace, generate_pkce


class OAuthClient:
    def __init__(self, config, proxy=None, verbose=True):
        self.oauth_issuer = config.get("oauth_issuer", "https://auth.openai.com")
        self.oauth_client_id = config.get("oauth_client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
        self.oauth_redirect_uri = config.get("oauth_redirect_uri", "http://localhost:1455/auth/callback")
        self.proxy = proxy
        self.verbose = verbose
        self.session = curl_requests.Session()
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

    def _log(self, message):
        if self.verbose:
            print(f"  [OAuth] {message}", flush=True)

    def login_and_get_tokens(self, email, password, device_id, user_agent=None, sec_ch_ua=None, impersonate=None, mail_client=None):
        self._log("开始 OAuth 登录流程...")
        code_verifier, code_challenge = generate_pkce()
        state = secrets.token_urlsafe(32)

        authorize_params = {
            "response_type": "code",
            "client_id": self.oauth_client_id,
            "redirect_uri": self.oauth_redirect_uri,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        authorize_url = f"{self.oauth_issuer}/oauth/authorize"
        self.session.cookies.set("oai-did", device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", device_id, domain="auth.openai.com")

        headers = {
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://chatgpt.com/",
        }

        has_login_session = False
        authorize_final_url = ""
        try:
            kwargs = {"params": authorize_params, "headers": headers, "allow_redirects": True, "timeout": 30}
            if impersonate:
                kwargs["impersonate"] = impersonate
            response = self.session.get(authorize_url, **kwargs)
            authorize_final_url = str(response.url)
            has_login_session = any((cookie.name if hasattr(cookie, "name") else str(cookie)) == "login_session" for cookie in self.session.cookies)
            self._log(f"/oauth/authorize -> {response.status_code}, login_session={'已获取' if has_login_session else '未获取'}")
        except Exception as exc:
            self._log(f"/oauth/authorize 异常: {exc}")

        if not has_login_session:
            try:
                oauth2_url = f"{self.oauth_issuer}/api/oauth/oauth2/auth"
                kwargs = {"params": authorize_params, "headers": headers, "allow_redirects": True, "timeout": 30}
                if impersonate:
                    kwargs["impersonate"] = impersonate
                response = self.session.get(oauth2_url, **kwargs)
                authorize_final_url = str(response.url)
                has_login_session = any((cookie.name if hasattr(cookie, "name") else str(cookie)) == "login_session" for cookie in self.session.cookies)
                self._log(f"/api/oauth/oauth2/auth -> {response.status_code}, login_session={'已获取' if has_login_session else '未获取'}")
            except Exception as exc:
                self._log(f"/api/oauth/oauth2/auth 异常: {exc}")

        if not authorize_final_url:
            return None

        continue_referer = authorize_final_url if authorize_final_url.startswith(self.oauth_issuer) else f"{self.oauth_issuer}/log-in"
        sentinel_token = build_sentinel_token(self.session, device_id, flow="authorize_continue", user_agent=user_agent, sec_ch_ua=sec_ch_ua, impersonate=impersonate)
        if not sentinel_token:
            self._log("无法获取 sentinel token (authorize_continue)")
            return None

        headers_continue = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": continue_referer,
            "Origin": self.oauth_issuer,
            "oai-device-id": device_id,
            "openai-sentinel-token": sentinel_token,
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        headers_continue.update(generate_datadog_trace())

        try:
            kwargs = {"json": {"username": {"kind": "email", "value": email}}, "headers": headers_continue, "timeout": 30, "allow_redirects": False}
            if impersonate:
                kwargs["impersonate"] = impersonate
            response = self.session.post(f"{self.oauth_issuer}/api/accounts/authorize/continue", **kwargs)
            if response.status_code != 200:
                self._log(f"提交邮箱失败: {response.text[:180]}")
                return None
            data = response.json()
            continue_url = data.get("continue_url", "")
            page_type = data.get("page", {}).get("type", "")
            self._log(f"continue page={page_type or '-'} next={continue_url[:80] if continue_url else '-'}")
        except Exception as exc:
            self._log(f"提交邮箱异常: {exc}")
            return None

        sentinel_pwd = build_sentinel_token(self.session, device_id, flow="password_verify", user_agent=user_agent, sec_ch_ua=sec_ch_ua, impersonate=impersonate)
        if not sentinel_pwd:
            self._log("无法获取 sentinel token (password_verify)")
            return None

        headers_verify = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.oauth_issuer}/log-in/password",
            "Origin": self.oauth_issuer,
            "oai-device-id": device_id,
            "openai-sentinel-token": sentinel_pwd,
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        headers_verify.update(generate_datadog_trace())

        try:
            kwargs = {"json": {"password": password}, "headers": headers_verify, "timeout": 30, "allow_redirects": False}
            if impersonate:
                kwargs["impersonate"] = impersonate
            response = self.session.post(f"{self.oauth_issuer}/api/accounts/password/verify", **kwargs)
            if response.status_code != 200:
                self._log(f"密码验证失败: {response.text[:180]}")
                return None
            verify_data = response.json()
            continue_url = verify_data.get("continue_url", "") or continue_url
            page_type = verify_data.get("page", {}).get("type", "") or page_type
            self._log(f"verify page={page_type or '-'} next={continue_url[:80] if continue_url else '-'}")
            need_oauth_otp = page_type == "email_otp_verification" or "email-verification" in (continue_url or "") or "email-otp" in (continue_url or "")
            if need_oauth_otp and mail_client:
                return self._handle_otp_verification(email, device_id, user_agent, sec_ch_ua, impersonate, mail_client, code_verifier, continue_url, page_type)
        except Exception as exc:
            self._log(f"密码验证异常: {exc}")
            return None

        code = None
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{self.oauth_issuer}{consent_url}"
        if consent_url:
            code = self._extract_code_from_url(consent_url)
        if not code and consent_url:
            self._log("跟随 continue_url 提取 code")
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{self.oauth_issuer}/log-in/password", user_agent=user_agent, impersonate=impersonate)

        consent_hint = any(
            token in (consent_url or "") for token in ["consent", "sign-in-with-chatgpt", "workspace", "organization"]
        ) or "consent" in page_type or "organization" in page_type

        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            code = self._oauth_submit_workspace_and_org(consent_url, device_id, user_agent, impersonate)

        if not code:
            fallback_consent = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            for retry in range(3):
                if retry > 0:
                    self._log(f"回退 consent 重试 ({retry + 1}/3)")
                    time.sleep(0.5)
                code = self._oauth_submit_workspace_and_org(fallback_consent, device_id, user_agent, impersonate)
                if code:
                    break
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{self.oauth_issuer}/log-in/password", user_agent=user_agent, impersonate=impersonate)
                if code:
                    break

        if not code:
            self._log("未获取到 authorization code")
            return None

        self._log(f"获取到 authorization code: {code[:20]}...")
        tokens = self._exchange_code_for_tokens(code, code_verifier, user_agent, impersonate)
        if tokens:
            self._log("OAuth 登录成功")
            return tokens
        self._log("换取 tokens 失败")
        return None

    def _extract_code_from_url(self, url):
        if not url or "code=" not in url:
            return None
        try:
            return parse_qs(urlparse(url).query).get("code", [None])[0]
        except Exception:
            return None

    def _oauth_follow_for_code(self, start_url, referer, user_agent, impersonate, max_hops=16):
        import re

        if "code=" in start_url:
            code = self._extract_code_from_url(start_url)
            if code:
                return code, start_url

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        if referer:
            headers["Referer"] = referer

        current_url = start_url
        last_url = start_url
        for hop in range(max_hops):
            try:
                kwargs = {"headers": headers, "allow_redirects": False, "timeout": 30}
                if impersonate:
                    kwargs["impersonate"] = impersonate
                response = self.session.get(current_url, **kwargs)
                last_url = str(response.url)
                self._log(f"follow[{hop + 1}] {response.status_code} {last_url[:80]}")
            except Exception as exc:
                maybe_localhost = re.search(r"(https?://localhost[^\s'\"]+)", str(exc))
                if maybe_localhost:
                    code = self._extract_code_from_url(maybe_localhost.group(1))
                    if code:
                        return code, maybe_localhost.group(1)
                self._log(f"follow[{hop + 1}] 异常: {str(exc)[:100]}")
                return None, last_url

            code = self._extract_code_from_url(last_url)
            if code:
                return code, last_url

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "")
                if not location:
                    return None, last_url
                if location.startswith("/"):
                    location = f"{self.oauth_issuer}{location}"
                code = self._extract_code_from_url(location)
                if code:
                    return code, location
                current_url = location
                headers["Referer"] = last_url
            else:
                return None, last_url
        return None, last_url

    def _oauth_submit_workspace_and_org(self, consent_url, device_id, user_agent, impersonate, max_retries=3):
        session_data = None
        for attempt in range(max_retries):
            session_data = self._decode_oauth_session_cookie()
            if session_data:
                break
            if attempt < max_retries - 1:
                time.sleep(0.3)
                try:
                    headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "User-Agent": user_agent or "Mozilla/5.0"}
                    kwargs = {"headers": headers, "allow_redirects": False, "timeout": 30}
                    if impersonate:
                        kwargs["impersonate"] = impersonate
                    self.session.get(consent_url, **kwargs)
                except Exception:
                    pass
        if not session_data:
            self._log("无法解码 oai-client-auth-session")
            return None

        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            return None
        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            return None

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": self.oauth_issuer,
            "Referer": consent_url,
            "User-Agent": user_agent or "Mozilla/5.0",
            "oai-device-id": device_id,
        }
        headers.update(generate_datadog_trace())

        try:
            kwargs = {"json": {"workspace_id": workspace_id}, "headers": headers, "allow_redirects": False, "timeout": 30}
            if impersonate:
                kwargs["impersonate"] = impersonate
            response = self.session.post(f"{self.oauth_issuer}/api/accounts/workspace/select", **kwargs)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "")
                if location.startswith("/"):
                    location = f"{self.oauth_issuer}{location}"
                return self._extract_code_from_url(location)
            if response.status_code == 200:
                data = response.json()
                orgs = data.get("data", {}).get("orgs", [])
                continue_url = data.get("continue_url", "")
                if orgs:
                    org_id = (orgs[0] or {}).get("id")
                    projects = (orgs[0] or {}).get("projects", [])
                    project_id = (projects[0] or {}).get("id") if projects else None
                    if org_id:
                        org_body = {"org_id": org_id}
                        if project_id:
                            org_body["project_id"] = project_id
                        headers["Referer"] = continue_url if continue_url and continue_url.startswith("http") else consent_url
                        kwargs = {"json": org_body, "headers": headers, "allow_redirects": False, "timeout": 30}
                        if impersonate:
                            kwargs["impersonate"] = impersonate
                        org_response = self.session.post(f"{self.oauth_issuer}/api/accounts/organization/select", **kwargs)
                        if org_response.status_code in (301, 302, 303, 307, 308):
                            location = org_response.headers.get("Location", "")
                            if location.startswith("/"):
                                location = f"{self.oauth_issuer}{location}"
                            code = self._extract_code_from_url(location)
                            if code:
                                return code
                        if org_response.status_code == 200:
                            org_data = org_response.json()
                            org_continue_url = org_data.get("continue_url", "")
                            if org_continue_url:
                                if org_continue_url.startswith("/"):
                                    org_continue_url = f"{self.oauth_issuer}{org_continue_url}"
                                code, _ = self._oauth_follow_for_code(org_continue_url, headers["Referer"], user_agent, impersonate)
                                if code:
                                    return code
                if continue_url:
                    if continue_url.startswith("/"):
                        continue_url = f"{self.oauth_issuer}{continue_url}"
                    code, _ = self._oauth_follow_for_code(continue_url, headers["Referer"], user_agent, impersonate)
                    if code:
                        return code
        except Exception as exc:
            self._log(f"workspace/select 异常: {exc}")
        return None

    def _decode_oauth_session_cookie(self):
        import base64
        import json

        def _decode_segment(raw):
            try:
                padded = raw + "=" * ((4 - len(raw) % 4) % 4)
                return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            except Exception:
                return None

        try:
            for cookie in self.session.cookies:
                name = cookie.name if hasattr(cookie, "name") else str(cookie)
                if name == "oai-client-auth-session":
                    value = cookie.value if hasattr(cookie, "value") else self.session.cookies.get(name)
                    if value:
                        if "." in value:
                            data = _decode_segment(value.split(".", 1)[0])
                            if data:
                                return data
                        data = _decode_segment(value)
                        if data:
                            return data
        except Exception:
            return None
        return None

    def _exchange_code_for_tokens(self, code, code_verifier, user_agent, impersonate):
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.oauth_redirect_uri,
            "client_id": self.oauth_client_id,
            "code_verifier": code_verifier,
        }
        try:
            kwargs = {"data": payload, "headers": headers, "timeout": 60}
            if impersonate:
                kwargs["impersonate"] = impersonate
            response = self.session.post(f"{self.oauth_issuer}/oauth/token", **kwargs)
            if response.status_code == 200:
                return response.json()
            self._log(f"换取 tokens 失败: {response.status_code} - {response.text[:200]}")
        except Exception as exc:
            self._log(f"换取 tokens 异常: {exc}")
        return None

    def _handle_otp_verification(self, email, device_id, user_agent, sec_ch_ua, impersonate, mail_client, code_verifier, continue_url, page_type):
        headers_otp = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.oauth_issuer}/email-verification",
            "Origin": self.oauth_issuer,
            "oai-device-id": device_id,
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        headers_otp.update(generate_datadog_trace())

        tried_codes = set()
        deadline = time.time() + 60
        while time.time() < deadline:
            otp_code = mail_client.wait_for_verification_code(email, timeout=10, exclude_codes=tried_codes)
            if not otp_code:
                continue
            tried_codes.add(otp_code)
            self._log(f"尝试 OAuth OTP: {otp_code}")
            try:
                kwargs = {"json": {"code": otp_code}, "headers": headers_otp, "timeout": 30, "allow_redirects": False}
                if impersonate:
                    kwargs["impersonate"] = impersonate
                response = self.session.post(f"{self.oauth_issuer}/api/accounts/email-otp/validate", **kwargs)
                if response.status_code != 200:
                    self._log(f"OTP 无效: {response.text[:160]}")
                    continue
                data = response.json()
                continue_url = data.get("continue_url", "") or continue_url
                page_type = data.get("page", {}).get("type", "") or page_type
                break
            except Exception as exc:
                self._log(f"OTP 验证异常: {exc}")
        else:
            self._log("OAuth 阶段 OTP 验证失败")
            return None

        code = None
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{self.oauth_issuer}{consent_url}"
        if consent_url:
            code = self._extract_code_from_url(consent_url)
        if not code and consent_url:
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{self.oauth_issuer}/email-verification", user_agent=user_agent, impersonate=impersonate)
        if not code:
            fallback_consent = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            code = self._oauth_submit_workspace_and_org(fallback_consent, device_id, user_agent, impersonate)
            if not code:
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{self.oauth_issuer}/email-verification", user_agent=user_agent, impersonate=impersonate)
        if not code:
            return None
        return self._exchange_code_for_tokens(code, code_verifier, user_agent, impersonate)
