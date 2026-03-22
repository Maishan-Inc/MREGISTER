"""
ChatGPT 注册客户端模块
使用 curl_cffi 模拟浏览器行为
"""

import random
import uuid
import time
from urllib.parse import urlparse, parse_qs

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print("❌ 需要安装 curl_cffi: pip install curl_cffi")
    import sys
    sys.exit(1)

from .sentinel_token import build_sentinel_token
from .utils import generate_datadog_trace


# Chrome 指纹配置
_CHROME_PROFILES = [
    {
        "major": 131, "impersonate": "chrome131",
        "build": 6778, "patch_range": (69, 205),
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "major": 133, "impersonate": "chrome133a",
        "build": 6943, "patch_range": (33, 153),
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    },
    {
        "major": 136, "impersonate": "chrome136",
        "build": 7103, "patch_range": (48, 175),
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    },
]


def _random_chrome_version():
    """随机选择一个 Chrome 版本"""
    profile = random.choice(_CHROME_PROFILES)
    major = profile["major"]
    build = profile["build"]
    patch = random.randint(*profile["patch_range"])
    full_ver = f"{major}.0.{build}.{patch}"
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36"
    return profile["impersonate"], major, full_ver, ua, profile["sec_ch_ua"]


class ChatGPTClient:
    """ChatGPT 注册客户端"""
    
    BASE = "https://chatgpt.com"
    AUTH = "https://auth.openai.com"
    
    def __init__(self, proxy=None, verbose=True):
        """
        初始化 ChatGPT 客户端
        
        Args:
            proxy: 代理地址
            verbose: 是否输出详细日志
        """
        self.proxy = proxy
        self.verbose = verbose
        self.device_id = str(uuid.uuid4())
        
        # 随机 Chrome 版本
        self.impersonate, self.chrome_major, self.chrome_full, self.ua, self.sec_ch_ua = _random_chrome_version()
        
        # 创建 session
        self.session = curl_requests.Session(impersonate=self.impersonate)
        
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
        
        # 设置基础 headers
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": random.choice([
                "en-US,en;q=0.9", "en-US,en;q=0.9,zh-CN;q=0.8",
                "en,en-US;q=0.9", "en-US,en;q=0.8",
            ]),
            "sec-ch-ua": self.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": f'"{self.chrome_full}"',
            "sec-ch-ua-platform-version": f'"{random.randint(10, 15)}.0.0"',
        })
        
        # 设置 oai-did cookie
        self.session.cookies.set("oai-did", self.device_id, domain="chatgpt.com")
    
    def _log(self, msg):
        """输出日志"""
        if self.verbose:
            print(f"  {msg}")
    
    def visit_homepage(self):
        """访问首页，建立 session"""
        self._log("访问 ChatGPT 首页...")
        url = f"{self.BASE}/"
        try:
            r = self.session.get(url, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            }, allow_redirects=True, timeout=30)
            return r.status_code == 200
        except Exception as e:
            self._log(f"访问首页失败: {e}")
            return False
    
    def get_csrf_token(self):
        """获取 CSRF token"""
        self._log("获取 CSRF token...")
        url = f"{self.BASE}/api/auth/csrf"
        try:
            r = self.session.get(url, headers={
                "Accept": "application/json",
                "Referer": f"{self.BASE}/"
            }, timeout=30)
            
            if r.status_code == 200:
                data = r.json()
                token = data.get("csrfToken", "")
                if token:
                    self._log(f"CSRF token: {token[:20]}...")
                    return token
        except Exception as e:
            self._log(f"获取 CSRF token 失败: {e}")
        
        return None
    
    def signin(self, email, csrf_token):
        """
        提交邮箱，获取 authorize URL
        
        Returns:
            str: authorize URL
        """
        self._log(f"提交邮箱: {email}")
        url = f"{self.BASE}/api/auth/signin/openai"
        
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
            r = self.session.post(
                url,
                params=params,
                data=form_data,
                headers=headers,
                timeout=30
            )
            
            if r.status_code == 200:
                data = r.json()
                authorize_url = data.get("url", "")
                if authorize_url:
                    self._log(f"获取到 authorize URL")
                    return authorize_url
        except Exception as e:
            self._log(f"提交邮箱失败: {e}")
        
        return None
    
    def authorize(self, url):
        """获取 CSRF token"""
        self._log("获取 CSRF token...")
        url = f"{self.BASE}/api/auth/csrf"
        try:
            r = self.session.get(url, headers={
                "Accept": "application/json",
                "Referer": f"{self.BASE}/"
            }, timeout=30)
            
            if r.status_code == 200:
                data = r.json()
                token = data.get("csrfToken", "")
                if token:
                    self._log(f"CSRF token: {token[:20]}...")
                    return token
        except Exception as e:
            self._log(f"获取 CSRF token 失败: {e}")
        
        return None
    
    def authorize(self, url, max_retries=3):
        """
        访问 authorize URL，跟随重定向（带重试机制）
        这是关键步骤，建立 auth.openai.com 的 session
        
        Returns:
            str: 最终重定向的 URL
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self._log(f"访问 authorize URL... (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(1)  # 重试前等待
                else:
                    self._log("访问 authorize URL...")
                
                r = self.session.get(url, headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": f"{self.BASE}/",
                    "Upgrade-Insecure-Requests": "1",
                }, allow_redirects=True, timeout=30)
                
                final_url = str(r.url)
                self._log(f"重定向到: {final_url}")
                return final_url
                
            except Exception as e:
                error_msg = str(e)
                is_tls_error = "TLS" in error_msg or "SSL" in error_msg or "curl: (35)" in error_msg
                
                if is_tls_error and attempt < max_retries - 1:
                    self._log(f"Authorize TLS 错误 (尝试 {attempt + 1}/{max_retries}): {error_msg[:100]}")
                    continue
                else:
                    self._log(f"Authorize 失败: {e}")
                    return ""
        
        return ""
    
    def callback(self):
        """完成注册回调"""
        self._log("执行回调...")
        url = f"{self.AUTH}/api/accounts/authorize/callback"
        try:
            r = self.session.get(url, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{self.AUTH}/about-you",
            }, allow_redirects=True, timeout=30)
            return r.status_code == 200
        except Exception as e:
            self._log(f"回调失败: {e}")
            return False
    
    def register_user(self, email, password):
        """
        注册用户（邮箱 + 密码）
        
        Returns:
            tuple: (success, message)
        """
        self._log(f"注册用户: {email}")
        url = f"{self.AUTH}/api/accounts/user/register"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.AUTH}/create-account/password",
            "Origin": self.AUTH,
        }
        headers.update(generate_datadog_trace())
        
        payload = {
            "username": email,
            "password": password,
        }
        
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if r.status_code == 200:
                data = r.json()
                self._log("注册成功")
                return True, "注册成功"
            else:
                try:
                    error_data = r.json()
                    error_msg = error_data.get("error", {}).get("message", r.text[:200])
                except:
                    error_msg = r.text[:200]
                self._log(f"注册失败: {r.status_code} - {error_msg}")
                return False, f"HTTP {r.status_code}: {error_msg}"
                
        except Exception as e:
            self._log(f"注册异常: {e}")
            return False, str(e)
    
    def send_email_otp(self):
        """触发发送邮箱验证码"""
        self._log("触发发送验证码...")
        url = f"{self.AUTH}/api/accounts/email-otp/send"
        
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.AUTH}/create-account/password",
            "Upgrade-Insecure-Requests": "1",
        }
        
        try:
            r = self.session.get(url, headers=headers, allow_redirects=True, timeout=30)
            return r.status_code == 200
        except Exception as e:
            self._log(f"发送验证码失败: {e}")
            return False
    
    def verify_email_otp(self, otp_code):
        """
        验证邮箱 OTP 码
        
        Args:
            otp_code: 6位验证码
            
        Returns:
            tuple: (success, message)
        """
        self._log(f"验证 OTP 码: {otp_code}")
        url = f"{self.AUTH}/api/accounts/email-otp/validate"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.AUTH}/email-verification",
            "Origin": self.AUTH,
        }
        headers.update(generate_datadog_trace())
        
        payload = {"code": otp_code}
        
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if r.status_code == 200:
                self._log("验证成功")
                return True, "验证成功"
            else:
                error_msg = r.text[:200]
                self._log(f"验证失败: {r.status_code} - {error_msg}")
                return False, f"HTTP {r.status_code}"
                
        except Exception as e:
            self._log(f"验证异常: {e}")
            return False, str(e)
    
    def create_account(self, first_name, last_name, birthdate):
        """
        完成账号创建（提交姓名和生日）
        
        Args:
            first_name: 名
            last_name: 姓
            birthdate: 生日 (YYYY-MM-DD)
            
        Returns:
            tuple: (success, message)
        """
        name = f"{first_name} {last_name}"
        self._log(f"完成账号创建: {name}")
        url = f"{self.AUTH}/api/accounts/create_account"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.AUTH}/about-you",
            "Origin": self.AUTH,
        }
        headers.update(generate_datadog_trace())
        
        payload = {
            "name": name,
            "birthdate": birthdate,
        }
        
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if r.status_code == 200:
                self._log("账号创建成功")
                return True, "账号创建成功"
            else:
                error_msg = r.text[:200]
                self._log(f"创建失败: {r.status_code} - {error_msg}")
                return False, f"HTTP {r.status_code}"
                
        except Exception as e:
            self._log(f"创建异常: {e}")
            return False, str(e)
    
    def register_complete_flow(self, email, password, first_name, last_name, birthdate, mail_client):
        """
        完整的注册流程（基于原版 run_register 方法）
        
        Args:
            email: 邮箱
            password: 密码
            first_name: 名
            last_name: 姓
            birthdate: 生日
            mail_client: 邮件客户端（用于获取验证码）
            
        Returns:
            tuple: (success, message)
        """
        from urllib.parse import urlparse
        
        # 1. 访问首页
        if not self.visit_homepage():
            return False, "访问首页失败"
        
        # 2. 获取 CSRF token
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            return False, "获取 CSRF token 失败"
        
        # 3. 提交邮箱，获取 authorize URL
        auth_url = self.signin(email, csrf_token)
        if not auth_url:
            return False, "提交邮箱失败"
        
        # 4. 访问 authorize URL（关键步骤！）
        final_url = self.authorize(auth_url)
        if not final_url:
            return False, "Authorize 失败"
        
        final_path = urlparse(final_url).path
        self._log(f"Authorize → {final_path}")
        
        # 5. 根据最终 URL 判断状态
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
        
        # 6. 处理 OTP 验证
        if need_otp:
            self._log("等待邮箱验证码...")
            otp_code = mail_client.wait_for_verification_code(email, timeout=30)
            if not otp_code:
                return False, "未收到验证码"
            
            success, msg = self.verify_email_otp(otp_code)
            if not success:
                return False, f"验证码失败: {msg}"
        
        # 7. 完成账号创建
        success, msg = self.create_account(first_name, last_name, birthdate)
        if not success:
            return False, f"创建账号失败: {msg}"
        
        self.callback()
        
        self._log("✅ 注册流程完成")
        return True, "注册成功"
