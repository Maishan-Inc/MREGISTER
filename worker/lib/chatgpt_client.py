import random
import time
import uuid
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print("❌ 需要安装 curl_cffi: pip install curl_cffi")
    raise

from .proxy_utils import normalize_proxy_url
from .utils import generate_datadog_trace

_CHROME_PROFILES = [
    {
        "major": 131,
        "impersonate": "chrome131",
        "build": 6778,
        "patch_range": (69, 205),
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "major": 133,
        "impersonate": "chrome133a",
        "build": 6943,
        "patch_range": (33, 153),
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    },
    {
        "major": 136,
        "impersonate": "chrome136",
        "build": 7103,
        "patch_range": (48, 175),
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    },
]


def _random_chrome_version():
    profile = random.choice(_CHROME_PROFILES)
    major = profile["major"]
    build = profile["build"]
    patch = random.randint(*profile["patch_range"])
    full_ver = f"{major}.0.{build}.{patch}"
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36"
    return profile["impersonate"], major, full_ver, ua, profile["sec_ch_ua"]


class ChatGPTClient:
    BASE = "https://chatgpt.com"
    AUTH = "https://auth.openai.com"

    def __init__(self, proxy=None, verbose=True):
        self.proxy = normalize_proxy_url(proxy)
        self.verbose = verbose
        self.device_id = str(uuid.uuid4())
        self.impersonate, self.chrome_major, self.chrome_full, self.ua, self.sec_ch_ua = _random_chrome_version()
        self.session = curl_requests.Session(impersonate=self.impersonate)
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": random.choice(["en-US,en;q=0.9", "en-US,en;q=0.9,zh-CN;q=0.8", "en,en-US;q=0.9", "en-US,en;q=0.8"]),
            "sec-ch-ua": self.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": f'"{self.chrome_full}"',
            "sec-ch-ua-platform-version": f'"{random.randint(10, 15)}.0.0"',
        })
        self.session.cookies.set("oai-did", self.device_id, domain="chatgpt.com")

    def _log(self, message):
        if self.verbose:
            print(f"  {message}", flush=True)

    def visit_homepage(self):
        self._log("访问 ChatGPT 首页...")
        try:
            response = self.session.get(
                f"{self.BASE}/",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                },
                allow_redirects=True,
                timeout=30,
            )
            return response.status_code == 200
        except Exception as exc:
            self._log(f"访问首页失败: {exc}")
            return False

    def get_csrf_token(self):
        self._log("获取 CSRF token...")
        try:
            response = self.session.get(
                f"{self.BASE}/api/auth/csrf",
                headers={"Accept": "application/json", "Referer": f"{self.BASE}/"},
                timeout=30,
            )
            if response.status_code == 200:
                token = response.json().get("csrfToken", "")
                if token:
                    self._log(f"CSRF token: {token[:20]}...")
                    return token
        except Exception as exc:
            self._log(f"获取 CSRF token 失败: {exc}")
        return None

    def signin(self, email, csrf_token):
        self._log(f"提交邮箱: {email}")
        params = {
            "prompt": "login",
            "ext-oai-did": self.device_id,
            "auth_session_logging_id": str(uuid.uuid4()),
            "screen_hint": "login_or_signup",
            "login_hint": email,
        }
        form_data = {
            "callbackUrl": f"{self.BASE}/",
            "csrfToken": csrf_token,
            "json": "true",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": f"{self.BASE}/",
            "Origin": self.BASE,
        }
        try:
            response = self.session.post(f"{self.BASE}/api/auth/signin/openai", params=params, data=form_data, headers=headers, timeout=30)
            if response.status_code == 200:
                authorize_url = response.json().get("url", "")
                if authorize_url:
                    self._log("获取到 authorize URL")
                    return authorize_url
        except Exception as exc:
            self._log(f"提交邮箱失败: {exc}")
        return None

    def authorize(self, url, max_retries=3):
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self._log(f"访问 authorize URL... (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(1)
                else:
                    self._log("访问 authorize URL...")
                response = self.session.get(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": f"{self.BASE}/",
                        "Upgrade-Insecure-Requests": "1",
                    },
                    allow_redirects=True,
                    timeout=30,
                )
                final_url = str(response.url)
                self._log(f"重定向到: {final_url}")
                return final_url
            except Exception as exc:
                error_msg = str(exc)
                if ("TLS" in error_msg or "SSL" in error_msg or "curl: (35)" in error_msg) and attempt < max_retries - 1:
                    self._log(f"Authorize TLS 错误: {error_msg[:100]}")
                    continue
                self._log(f"Authorize 失败: {exc}")
                return ""
        return ""

    def callback(self):
        self._log("执行回调...")
        try:
            response = self.session.get(
                f"{self.AUTH}/api/accounts/authorize/callback",
                headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": f"{self.AUTH}/about-you"},
                allow_redirects=True,
                timeout=30,
            )
            return response.status_code == 200
        except Exception as exc:
            self._log(f"回调失败: {exc}")
            return False

    def register_user(self, email, password):
        self._log(f"注册用户: {email}")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.AUTH}/create-account/password",
            "Origin": self.AUTH,
        }
        headers.update(generate_datadog_trace())
        try:
            response = self.session.post(
                f"{self.AUTH}/api/accounts/user/register",
                json={"username": email, "password": password},
                headers=headers,
                timeout=30,
            )
            if response.status_code == 200:
                self._log("注册成功")
                return True, "注册成功"
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text[:200])
            except Exception:
                error_msg = response.text[:200]
            self._log(f"注册失败: {response.status_code} - {error_msg}")
            return False, f"HTTP {response.status_code}: {error_msg}"
        except Exception as exc:
            self._log(f"注册异常: {exc}")
            return False, str(exc)

    def send_email_otp(self):
        self._log("触发发送验证码...")
        try:
            response = self.session.get(
                f"{self.AUTH}/api/accounts/email-otp/send",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": f"{self.AUTH}/create-account/password",
                    "Upgrade-Insecure-Requests": "1",
                },
                allow_redirects=True,
                timeout=30,
            )
            return response.status_code == 200
        except Exception as exc:
            self._log(f"发送验证码失败: {exc}")
            return False

    def verify_email_otp(self, otp_code):
        self._log(f"验证 OTP 码: {otp_code}")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.AUTH}/email-verification",
            "Origin": self.AUTH,
        }
        headers.update(generate_datadog_trace())
        try:
            response = self.session.post(
                f"{self.AUTH}/api/accounts/email-otp/validate",
                json={"code": otp_code},
                headers=headers,
                timeout=30,
            )
            if response.status_code == 200:
                self._log("验证成功")
                return True, "验证成功"
            self._log(f"验证失败: {response.status_code} - {response.text[:200]}")
            return False, f"HTTP {response.status_code}"
        except Exception as exc:
            self._log(f"验证异常: {exc}")
            return False, str(exc)

    def create_account(self, first_name, last_name, birthdate):
        name = f"{first_name} {last_name}"
        self._log(f"完成账号创建: {name}")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.AUTH}/about-you",
            "Origin": self.AUTH,
        }
        headers.update(generate_datadog_trace())
        try:
            response = self.session.post(
                f"{self.AUTH}/api/accounts/create_account",
                json={"name": name, "birthdate": birthdate},
                headers=headers,
                timeout=30,
            )
            if response.status_code == 200:
                self._log("账号创建成功")
                return True, "账号创建成功"
            self._log(f"创建失败: {response.status_code} - {response.text[:200]}")
            return False, f"HTTP {response.status_code}"
        except Exception as exc:
            self._log(f"创建异常: {exc}")
            return False, str(exc)

    def register_complete_flow(self, email, password, first_name, last_name, birthdate, mail_client):
        if not self.visit_homepage():
            return False, "访问首页失败"
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            return False, "获取 CSRF token 失败"
        auth_url = self.signin(email, csrf_token)
        if not auth_url:
            return False, "提交邮箱失败"
        final_url = self.authorize(auth_url)
        if not final_url:
            return False, "Authorize 失败"

        final_path = urlparse(final_url).path
        self._log(f"Authorize -> {final_path}")
        need_otp = False

        if "create-account/password" in final_path:
            self._log("全新注册流程")
            success, msg = self.register_user(email, password)
            if not success:
                return False, f"注册失败: {msg}"
            self.send_email_otp()
            need_otp = True
        elif "email-verification" in final_path or "email-otp" in final_path:
            self._log("跳到 OTP 验证阶段")
            need_otp = True
        elif "about-you" in final_path:
            self._log("跳到填写信息阶段")
            success, msg = self.create_account(first_name, last_name, birthdate)
            if not success:
                return False, f"创建账号失败: {msg}"
            self.callback()
            return True, "注册成功"
        elif "callback" in final_path or "chatgpt.com" in final_url:
            self._log("账号已完成注册")
            return True, "账号已完成注册"
        else:
            self._log(f"未知跳转: {final_url}")
            success, msg = self.register_user(email, password)
            if not success:
                return False, f"注册失败: {msg}"
            self.send_email_otp()
            need_otp = True

        if need_otp:
            self._log("等待邮箱验证码...")
            otp_code = mail_client.wait_for_verification_code(email, timeout=60)
            if not otp_code:
                return False, "未收到验证码"
            success, msg = self.verify_email_otp(otp_code)
            if not success:
                return False, f"验证码失败: {msg}"

        success, msg = self.create_account(first_name, last_name, birthdate)
        if not success:
            return False, f"创建账号失败: {msg}"
        self.callback()
        self._log("注册流程完成")
        return True, "注册成功"
