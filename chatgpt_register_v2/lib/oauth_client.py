"""
OAuth 客户端模块 - 处理 Codex OAuth 登录流程
"""

import time
import secrets
from urllib.parse import urlparse, parse_qs

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    import requests as curl_requests

from .utils import generate_pkce, generate_datadog_trace
from .sentinel_token import build_sentinel_token


class OAuthClient:
    """OAuth 客户端 - 用于获取 Access Token 和 Refresh Token"""
    
    def __init__(self, config, proxy=None, verbose=True):
        """
        初始化 OAuth 客户端
        
        Args:
            config: 配置字典
            proxy: 代理地址
            verbose: 是否输出详细日志
        """
        self.oauth_issuer = config.get("oauth_issuer", "https://auth.openai.com")
        self.oauth_client_id = config.get("oauth_client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
        self.oauth_redirect_uri = config.get("oauth_redirect_uri", "http://localhost:1455/auth/callback")
        self.proxy = proxy
        self.verbose = verbose
        
        # 创建 session
        self.session = curl_requests.Session()
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
    
    def _log(self, msg):
        """输出日志"""
        if self.verbose:
            print(f"  [OAuth] {msg}")
    
    def login_and_get_tokens(self, email, password, device_id, user_agent=None, sec_ch_ua=None, impersonate=None, mail_client=None):
        """
        完整的 OAuth 登录流程，获取 tokens
        
        Args:
            email: 邮箱
            password: 密码
            device_id: 设备 ID
            user_agent: User-Agent
            sec_ch_ua: sec-ch-ua header
            impersonate: curl_cffi impersonate 参数
            mail_client: 邮件客户端（用于获取 OTP，如果需要）
            
        Returns:
            dict: tokens 字典，包含 access_token, refresh_token, id_token
        """
        self._log("开始 OAuth 登录流程...")
        
        # 1. 生成 PKCE 参数
        code_verifier, code_challenge = generate_pkce()
        state = secrets.token_urlsafe(32)
        
        # 2. Bootstrap OAuth session - 确保获取 login_session cookie
        self._log("步骤1: Bootstrap OAuth session...")
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
        
        # 确保 oai-did cookie 在两个域上都设置
        self.session.cookies.set("oai-did", device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", device_id, domain="auth.openai.com")
        
        # 第一次尝试：GET /oauth/authorize
        has_login_session = False
        authorize_final_url = ""
        
        try:
            headers = {
                "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
                "Referer": "https://chatgpt.com/",
            }
            
            kwargs = {"params": authorize_params, "headers": headers, "allow_redirects": True, "timeout": 30}
            if impersonate:
                kwargs["impersonate"] = impersonate
            
            r = self.session.get(authorize_url, **kwargs)
            authorize_final_url = str(r.url)
            redirects = len(getattr(r, "history", []) or [])
            
            self._log(f"/oauth/authorize -> {r.status_code}, redirects={redirects}")
            
            # 检查是否获取到 login_session cookie
            has_login_session = any(
                (cookie.name if hasattr(cookie, 'name') else str(cookie)) == "login_session"
                for cookie in self.session.cookies
            )
            
            self._log(f"login_session: {'已获取' if has_login_session else '未获取'}")
            
        except Exception as e:
            self._log(f"/oauth/authorize 异常: {e}")
        
        # 如果没有获取到 login_session，尝试 oauth2/auth 入口
        if not has_login_session:
            self._log("未获取到 login_session，尝试 /api/oauth/oauth2/auth...")
            try:
                oauth2_url = f"{self.oauth_issuer}/api/oauth/oauth2/auth"
                kwargs = {"params": authorize_params, "headers": headers, "allow_redirects": True, "timeout": 30}
                if impersonate:
                    kwargs["impersonate"] = impersonate
                
                r2 = self.session.get(oauth2_url, **kwargs)
                authorize_final_url = str(r2.url)
                redirects2 = len(getattr(r2, "history", []) or [])
                
                self._log(f"/api/oauth/oauth2/auth -> {r2.status_code}, redirects={redirects2}")
                
                has_login_session = any(
                    (cookie.name if hasattr(cookie, 'name') else str(cookie)) == "login_session"
                    for cookie in self.session.cookies
                )
                
                self._log(f"login_session(重试): {'已获取' if has_login_session else '未获取'}")
                
            except Exception as e:
                self._log(f"/api/oauth/oauth2/auth 异常: {e}")
        
        if not authorize_final_url:
            self._log("Bootstrap 失败")
            return None
        
        # 确定 continue_referer
        continue_referer = authorize_final_url if authorize_final_url.startswith(self.oauth_issuer) else f"{self.oauth_issuer}/log-in"
        
        # 3. 提交邮箱
        self._log("步骤2: POST /api/accounts/authorize/continue")
        sentinel_token = build_sentinel_token(
            self.session, device_id, flow="authorize_continue",
            user_agent=user_agent, sec_ch_ua=sec_ch_ua, impersonate=impersonate
        )
        
        if not sentinel_token:
            self._log("无法获取 sentinel token (authorize_continue)")
            return None
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": continue_referer,
            "Origin": self.oauth_issuer,
            "oai-device-id": device_id,
            "openai-sentinel-token": sentinel_token,
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        headers.update(generate_datadog_trace())
        
        payload = {
            "username": {"kind": "email", "value": email},
        }
        
        try:
            kwargs = {"json": payload, "headers": headers, "timeout": 30, "allow_redirects": False}
            if impersonate:
                kwargs["impersonate"] = impersonate
            
            r = self.session.post(
                f"{self.oauth_issuer}/api/accounts/authorize/continue",
                **kwargs
            )
            
            self._log(f"/authorize/continue -> {r.status_code}")
            
            # 如果是 400 且包含 invalid_auth_step，重新 bootstrap
            if r.status_code == 400 and "invalid_auth_step" in (r.text or ""):
                self._log("invalid_auth_step，重新 bootstrap...")
                # 重新执行 bootstrap
                try:
                    kwargs_retry = {"params": authorize_params, "headers": {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": "https://chatgpt.com/"}, "allow_redirects": True, "timeout": 30}
                    if impersonate:
                        kwargs_retry["impersonate"] = impersonate
                    r_retry = self.session.get(authorize_url, **kwargs_retry)
                    authorize_final_url = str(r_retry.url)
                    continue_referer = authorize_final_url if authorize_final_url.startswith(self.oauth_issuer) else f"{self.oauth_issuer}/log-in"
                    
                    # 重新提交
                    headers["Referer"] = continue_referer
                    headers.update(generate_datadog_trace())
                    kwargs = {"json": payload, "headers": headers, "timeout": 30, "allow_redirects": False}
                    if impersonate:
                        kwargs["impersonate"] = impersonate
                    r = self.session.post(f"{self.oauth_issuer}/api/accounts/authorize/continue", **kwargs)
                    self._log(f"/authorize/continue(重试) -> {r.status_code}")
                except Exception as e:
                    self._log(f"重试异常: {e}")
            
            if r.status_code != 200:
                self._log(f"提交邮箱失败: {r.text[:180]}")
                return None
            
            data = r.json()
            continue_url = data.get("continue_url", "")
            page_type = data.get("page", {}).get("type", "")
            self._log(f"continue page={page_type or '-'} next={continue_url[:80] if continue_url else '-'}...")
            
        except Exception as e:
            self._log(f"提交邮箱异常: {e}")
            return None
        
        # 4. 提交密码
        self._log("步骤3: POST /api/accounts/password/verify")
        sentinel_pwd = build_sentinel_token(
            self.session, device_id, flow="password_verify",
            user_agent=user_agent, sec_ch_ua=sec_ch_ua, impersonate=impersonate
        )
        
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
        
        payload_pwd = {"password": password}
        
        try:
            kwargs = {"json": payload_pwd, "headers": headers_verify, "timeout": 30, "allow_redirects": False}
            if impersonate:
                kwargs["impersonate"] = impersonate
            
            r = self.session.post(
                f"{self.oauth_issuer}/api/accounts/password/verify",
                **kwargs
            )
            
            self._log(f"/password/verify -> {r.status_code}")
            
            if r.status_code != 200:
                self._log(f"密码验证失败: {r.text[:180]}")
                return None
            
            verify_data = r.json()
            continue_url = verify_data.get("continue_url", "") or continue_url
            page_type = verify_data.get("page", {}).get("type", "") or page_type
            self._log(f"verify page={page_type or '-'} next={continue_url[:80] if continue_url else '-'}...")
            
            # 检查是否需要 OTP
            need_oauth_otp = (
                page_type == "email_otp_verification"
                or "email-verification" in (continue_url or "")
                or "email-otp" in (continue_url or "")
            )
            
            if need_oauth_otp and mail_client:
                self._log("检测到需要邮箱 OTP 验证")
                return self._handle_otp_verification(
                    email, device_id, user_agent, sec_ch_ua,
                    impersonate, mail_client, code_verifier, continue_url, page_type
                )
            
        except Exception as e:
            self._log(f"密码验证异常: {e}")
            return None
        
        # 5. 处理 consent 流程
        self._log("步骤4: 处理 consent 流程...")
        code = None
        consent_url = continue_url
        
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{self.oauth_issuer}{consent_url}"
        
        if not consent_url and "consent" in page_type:
            consent_url = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
        
        # 先检查 URL 中是否已经包含 code
        if consent_url:
            code = self._extract_code_from_url(consent_url)
        
        # 跟随 continue_url
        if not code and consent_url:
            self._log("步骤5: 跟随 continue_url 提取 code")
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{self.oauth_issuer}/log-in/password", user_agent=user_agent, impersonate=impersonate)
        
        # 检查是否需要 workspace/org 选择
        consent_hint = (
            ("consent" in (consent_url or ""))
            or ("sign-in-with-chatgpt" in (consent_url or ""))
            or ("workspace" in (consent_url or ""))
            or ("organization" in (consent_url or ""))
            or ("consent" in page_type)
            or ("organization" in page_type)
        )
        
        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            self._log("步骤6: 执行 workspace/org 选择")
            code = self._oauth_submit_workspace_and_org(consent_url, device_id, user_agent, impersonate)
        
        # 最后回退（带重试机制）
        if not code:
            fallback_consent = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            
            # 尝试最多 3 次
            for retry in range(3):
                if retry > 0:
                    self._log(f"步骤6: 回退 consent 路径重试 (尝试 {retry + 1}/3)")
                    time.sleep(0.5)  # 短暂延迟
                else:
                    self._log("步骤6: 回退 consent 路径重试")
                
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
        
        # 6. 用 code 换取 tokens
        self._log("步骤7: POST /oauth/token")
        tokens = self._exchange_code_for_tokens(code, code_verifier, user_agent, impersonate)
        
        if tokens:
            self._log("✅ OAuth 登录成功")
            return tokens
        else:
            self._log("换取 tokens 失败")
            return None
    
    def _extract_code_from_url(self, url):
        """从 URL 中提取 code"""
        if not url or "code=" not in url:
            return None
        try:
            return parse_qs(urlparse(url).query).get("code", [None])[0]
        except Exception:
            return None
    
    def _oauth_follow_for_code(self, start_url, referer, user_agent, impersonate, max_hops=16):
        """跟随 URL 获取 authorization code（手动跟随重定向）"""
        import re
        
        # 先检查 URL 中是否已经包含 code
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
                
                r = self.session.get(current_url, **kwargs)
                last_url = str(r.url)
                self._log(f"follow[{hop+1}] {r.status_code} {last_url[:80]}")
                
            except Exception as e:
                # 从异常中提取 localhost URL
                maybe_localhost = re.search(r'(https?://localhost[^\s\'\"]+)', str(e))
                if maybe_localhost:
                    code = self._extract_code_from_url(maybe_localhost.group(1))
                    if code:
                        self._log(f"从 localhost 异常提取到 code")
                        return code, maybe_localhost.group(1)
                self._log(f"follow[{hop+1}] 异常: {str(e)[:100]}")
                return None, last_url
            
            # 检查当前 URL
            code = self._extract_code_from_url(last_url)
            if code:
                return code, last_url
            
            # 检查重定向
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
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
                # 不是重定向，立即返回（原始代码的逻辑）
                return None, last_url
        
        return None, last_url
    
    def _oauth_submit_workspace_and_org(self, consent_url, device_id, user_agent, impersonate, max_retries=3):
        """提交 workspace 和 organization 选择（带重试）"""
        session_data = None
        
        # 尝试多次解码 cookie
        for attempt in range(max_retries):
            session_data = self._decode_oauth_session_cookie()
            if session_data:
                break
            
            if attempt < max_retries - 1:
                self._log(f"无法解码 oai-client-auth-session (尝试 {attempt + 1}/{max_retries})")
                time.sleep(0.3)  # 短暂延迟后重试
                
                # 重新访问 consent URL 以确保 cookie 被设置
                try:
                    headers = {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "User-Agent": user_agent or "Mozilla/5.0",
                    }
                    kwargs = {"headers": headers, "allow_redirects": False, "timeout": 30}
                    if impersonate:
                        kwargs["impersonate"] = impersonate
                    self.session.get(consent_url, **kwargs)
                except Exception:
                    pass
            else:
                self._log("无法解码 oai-client-auth-session")
                return None
        
        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            self._log("session 中没有 workspace 信息")
            return None
        
        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            self._log("workspace_id 为空")
            return None
        
        self._log(f"选择 workspace: {workspace_id}")
        
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
            kwargs = {
                "json": {"workspace_id": workspace_id},
                "headers": headers,
                "allow_redirects": False,
                "timeout": 30
            }
            if impersonate:
                kwargs["impersonate"] = impersonate
            
            r = self.session.post(
                f"{self.oauth_issuer}/api/accounts/workspace/select",
                **kwargs
            )
            
            self._log(f"workspace/select -> {r.status_code}")
            
            # 检查重定向
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
                if location.startswith("/"):
                    location = f"{self.oauth_issuer}{location}"
                if "code=" in location:
                    code = self._extract_code_from_url(location)
                    if code:
                        self._log("从 workspace/select 重定向获取到 code")
                        return code
            
            # 如果返回 200，检查响应中的 orgs
            if r.status_code == 200:
                try:
                    data = r.json()
                    orgs = data.get("data", {}).get("orgs", [])
                    continue_url = data.get("continue_url", "")
                    
                    if orgs:
                        org_id = (orgs[0] or {}).get("id")
                        projects = (orgs[0] or {}).get("projects", [])
                        project_id = (projects[0] or {}).get("id") if projects else None
                        
                        if org_id:
                            self._log(f"选择 organization: {org_id}")
                            
                            org_body = {"org_id": org_id}
                            if project_id:
                                org_body["project_id"] = project_id
                            
                            headers["Referer"] = continue_url if continue_url and continue_url.startswith("http") else consent_url
                            
                            kwargs = {
                                "json": org_body,
                                "headers": headers,
                                "allow_redirects": False,
                                "timeout": 30
                            }
                            if impersonate:
                                kwargs["impersonate"] = impersonate
                            
                            r_org = self.session.post(
                                f"{self.oauth_issuer}/api/accounts/organization/select",
                                **kwargs
                            )
                            
                            self._log(f"organization/select -> {r_org.status_code}")
                            
                            # 检查重定向
                            if r_org.status_code in (301, 302, 303, 307, 308):
                                location = r_org.headers.get("Location", "")
                                if location.startswith("/"):
                                    location = f"{self.oauth_issuer}{location}"
                                if "code=" in location:
                                    code = self._extract_code_from_url(location)
                                    if code:
                                        self._log("从 organization/select 重定向获取到 code")
                                        return code
                            
                            # 检查 continue_url
                            if r_org.status_code == 200:
                                try:
                                    org_data = r_org.json()
                                    org_continue_url = org_data.get("continue_url", "")
                                    org_page = org_data.get("page", {}).get("type", "")
                                    self._log(f"organization/select page={org_page or '-'} continue_url={org_continue_url[:80] if org_continue_url else 'None'}...")
                                    
                                    if org_continue_url:
                                        if org_continue_url.startswith("/"):
                                            org_continue_url = f"{self.oauth_issuer}{org_continue_url}"
                                        # 跟随 continue_url
                                        code, _ = self._oauth_follow_for_code(org_continue_url, headers["Referer"], user_agent, impersonate)
                                        if code:
                                            return code
                                except Exception as e:
                                    self._log(f"解析 organization/select 响应异常: {e}")
                    
                    # 如果有 continue_url，跟随它
                    if continue_url:
                        if continue_url.startswith("/"):
                            continue_url = f"{self.oauth_issuer}{continue_url}"
                        code, _ = self._oauth_follow_for_code(continue_url, headers["Referer"], user_agent, impersonate)
                        if code:
                            return code
                        
                except Exception as e:
                    self._log(f"处理 workspace/select 响应异常: {e}")
        
        except Exception as e:
            self._log(f"workspace/select 异常: {e}")
        
        return None
    
    def _decode_oauth_session_cookie(self):
        """解码 oai-client-auth-session cookie"""
        import json
        import base64
        
        try:
            for cookie in self.session.cookies:
                try:
                    name = cookie.name if hasattr(cookie, 'name') else str(cookie)
                    if name == "oai-client-auth-session":
                        value = cookie.value if hasattr(cookie, 'value') else self.session.cookies.get(name)
                        if value:
                            # 解码 base64
                            decoded = base64.b64decode(value).decode('utf-8')
                            data = json.loads(decoded)
                            return data
                except Exception:
                    continue
        except Exception:
            pass
        
        return None
    
    def _exchange_code_for_tokens(self, code, code_verifier, user_agent, impersonate):
        """用 authorization code 换取 tokens"""
        url = f"{self.oauth_issuer}/oauth/token"
        
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.oauth_redirect_uri,
            "client_id": self.oauth_client_id,
            "code_verifier": code_verifier,
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        
        try:
            kwargs = {"data": payload, "headers": headers, "timeout": 60}
            if impersonate:
                kwargs["impersonate"] = impersonate
            
            r = self.session.post(url, **kwargs)
            
            if r.status_code == 200:
                return r.json()
            else:
                self._log(f"换取 tokens 失败: {r.status_code} - {r.text[:200]}")
                
        except Exception as e:
            self._log(f"换取 tokens 异常: {e}")
        
        return None
    
    def _handle_otp_verification(self, email, device_id, user_agent, sec_ch_ua, impersonate, mail_client, code_verifier, continue_url, page_type):
        """处理 OTP 验证流程"""
        self._log("步骤4: 检测到邮箱 OTP 验证")
        
        # 获取已使用的验证码（从 mail_client 的历史记录中）
        exclude_codes = getattr(mail_client, '_used_codes', set())
        
        headers_otp = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.oauth_issuer}/email-verification",
            "Origin": self.oauth_issuer,
            "oai-device-id": device_id,
            "User-Agent": user_agent or "Mozilla/5.0",
        }
        headers_otp.update(generate_datadog_trace())
        
        tried_codes = set(exclude_codes)
        otp_success = False
        otp_deadline = time.time() + 30
        
        while time.time() < otp_deadline and not otp_success:
            # 获取邮件列表
            messages = mail_client.fetch_emails(email) or []
            candidate_codes = []
            
            for msg in messages[:12]:
                content = msg.get("content") or msg.get("text") or ""
                code = mail_client.extract_verification_code(content)
                if code and code not in tried_codes:
                    candidate_codes.append(code)
            
            if not candidate_codes:
                elapsed = int(30 - max(0, otp_deadline - time.time()))
                self._log(f"OTP 等待中... ({elapsed}s/30s)")
                time.sleep(2)
                continue
            
            for otp_code in candidate_codes:
                tried_codes.add(otp_code)
                self._log(f"尝试 OTP: {otp_code}")
                
                try:
                    kwargs = {
                        "json": {"code": otp_code},
                        "headers": headers_otp,
                        "timeout": 30,
                        "allow_redirects": False
                    }
                    if impersonate:
                        kwargs["impersonate"] = impersonate
                    
                    resp_otp = self.session.post(
                        f"{self.oauth_issuer}/api/accounts/email-otp/validate",
                        **kwargs
                    )
                except Exception as e:
                    self._log(f"email-otp/validate 异常: {e}")
                    continue
                
                self._log(f"/email-otp/validate -> {resp_otp.status_code}")
                
                if resp_otp.status_code != 200:
                    self._log(f"OTP 无效，继续尝试下一条: {resp_otp.text[:160]}")
                    continue
                
                try:
                    otp_data = resp_otp.json()
                except Exception:
                    self._log("email-otp/validate 响应解析失败")
                    continue
                
                continue_url = otp_data.get("continue_url", "") or continue_url
                page_type = otp_data.get("page", {}).get("type", "") or page_type
                self._log(f"OTP 验证通过 page={page_type or '-'} next={continue_url[:80] if continue_url else '-'}...")
                otp_success = True
                
                # 记录已使用的验证码
                if not hasattr(mail_client, '_used_codes'):
                    mail_client._used_codes = set()
                mail_client._used_codes.add(otp_code)
                
                break
            
            if not otp_success:
                time.sleep(2)
        
        if not otp_success:
            self._log(f"OAuth 阶段 OTP 验证失败，已尝试 {len(tried_codes)} 个验证码")
            return None
        
        # OTP 验证成功后，继续 consent 流程
        code = None
        consent_url = continue_url
        
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{self.oauth_issuer}{consent_url}"
        
        if not consent_url and "consent" in page_type:
            consent_url = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
        
        # 先检查 URL 中是否已经包含 code
        if consent_url:
            code = self._extract_code_from_url(consent_url)
        
        # 跟随 continue_url
        if not code and consent_url:
            self._log("步骤5: 跟随 continue_url 提取 code")
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{self.oauth_issuer}/email-verification", user_agent=user_agent, impersonate=impersonate)
        
        # 检查是否需要 workspace/org 选择
        consent_hint = (
            ("consent" in (consent_url or ""))
            or ("sign-in-with-chatgpt" in (consent_url or ""))
            or ("workspace" in (consent_url or ""))
            or ("organization" in (consent_url or ""))
            or ("consent" in page_type)
            or ("organization" in page_type)
        )
        
        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            self._log("步骤6: 执行 workspace/org 选择")
            code = self._oauth_submit_workspace_and_org(consent_url, device_id, user_agent, impersonate)
        
        # 最后回退
        if not code:
            fallback_consent = f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent"
            self._log("步骤6: 回退 consent 路径重试")
            code = self._oauth_submit_workspace_and_org(fallback_consent, device_id, user_agent, impersonate)
            if not code:
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{self.oauth_issuer}/email-verification", user_agent=user_agent, impersonate=impersonate)
        
        if not code:
            self._log("未获取到 authorization code")
            return None
        
        self._log(f"获取到 authorization code: {code[:20]}...")
        
        # 用 code 换取 tokens
        self._log("步骤7: POST /oauth/token")
        tokens = self._exchange_code_for_tokens(code, code_verifier, user_agent, impersonate)
        
        if tokens:
            self._log("✅ OAuth 登录成功")
            return tokens
        else:
            self._log("换取 tokens 失败")
            return None
