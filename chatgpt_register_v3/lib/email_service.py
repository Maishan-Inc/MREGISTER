"""
邮箱服务适配器模块
复用 chatgpt_register_v2 的邮箱客户端实现
"""

import os
import sys
from typing import Any, Dict, Optional

from .constants import EmailServiceType
from .proxy_utils import normalize_proxy_url


_v2_lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "chatgpt_register_v2", "lib")
if os.path.exists(_v2_lib_path) and _v2_lib_path not in sys.path:
    sys.path.insert(0, _v2_lib_path)


class EmailServiceError(Exception):
    """邮箱服务异常"""
    pass


class EmailServiceStatus:
    """邮箱服务状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class BaseEmailService:
    """邮箱服务抽象基类"""

    def __init__(self, service_type: EmailServiceType, name: str = None):
        self.service_type = service_type
        self.name = name or f"{service_type.value}_service"
        self._status = EmailServiceStatus.HEALTHY
        self._last_error = None

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        pattern: str = r"(?<!\d)(\d{6})(?!\d)",
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        raise NotImplementedError

    def list_emails(self, **kwargs) -> list:
        raise NotImplementedError

    def delete_email(self, email_id: str) -> bool:
        raise NotImplementedError

    def check_health(self) -> bool:
        raise NotImplementedError


def create_email_service(
    config: Dict[str, Any],
    proxy_url: Optional[str] = None
) -> BaseEmailService:
    """创建邮箱服务实例"""
    provider = str(config.get("mail_provider", "skymail")).lower().replace("-", "_")
    normalized_proxy = normalize_proxy_url(proxy_url)

    # 导入v2的邮箱客户端
    try:
        from skymail_client import (
            SkymailClient, GPTMailAdapter, MoeMailAdapter, 
            CloudflareTempEmailAdapter, init_skymail_client
        )
    except ImportError:
        from chatgpt_register_v2.lib.skymail_client import (
            SkymailClient, GPTMailAdapter, MoeMailAdapter,
            CloudflareTempEmailAdapter, init_skymail_client
        )

    if provider == "gptmail":
        api_key = str(config.get("mail_api_key") or config.get("gptmail_api_key") or "").strip()
        base_url = str(config.get("mail_base_url") or config.get("gptmail_base_url") or "https://mail.chatgpt.org.uk").strip()
        prefix = str(config.get("mail_prefix") or config.get("gptmail_prefix") or "").strip() or None
        domain = str(config.get("mail_domain") or config.get("gptmail_domain") or "").strip() or None
        timeout = float(config.get("mail_timeout") or config.get("gptmail_timeout") or 30)

        if not api_key:
            print("错误: 未配置 GPTMail API Key")
            sys.exit(1)

        service = GPTMailAdapter(
            base_url=base_url,
            api_key=api_key,
            proxy=normalized_proxy,
            prefix=prefix,
            domain=domain,
            timeout=timeout,
        )
        service.service_type = EmailServiceType.GPTMAIL
        return service

    if provider in ("moemail", "moe_mail"):
        api_key = str(config.get("mail_api_key") or "").strip()
        base_url = str(config.get("mail_base_url") or "").strip()
        prefix = str(config.get("mail_prefix") or "").strip() or None
        domain = str(config.get("mail_domain") or "").strip() or None
        timeout = float(config.get("mail_timeout") or 30)
        expiry_time = int(config.get("mail_expiry_time") or 3600000)

        if not api_key:
            print("错误: 未配置 MoeMail API Key")
            sys.exit(1)
        if not base_url:
            print("错误: 未配置 MoeMail Base URL")
            sys.exit(1)

        service = MoeMailAdapter(
            base_url=base_url,
            api_key=api_key,
            proxy=normalized_proxy,
            prefix=prefix,
            domain=domain,
            timeout=timeout,
            expiry_time=expiry_time,
        )
        service.service_type = EmailServiceType.MOEMAIL
        return service

    if provider in ("cloudflare_temp_email", "cloudflare"):
        api_key = str(config.get("mail_api_key") or "").strip()
        base_url = str(config.get("mail_base_url") or "").strip()
        prefix = str(config.get("mail_prefix") or "").strip() or None
        domain = str(config.get("mail_domain") or "").strip() or None
        secret = str(config.get("mail_secret") or "").strip() or None
        timeout = float(config.get("mail_timeout") or 30)

        if not api_key:
            print("错误: 未配置 Cloudflare Temp Email 管理密钥")
            sys.exit(1)
        if not base_url:
            print("错误: 未配置 Cloudflare Temp Email Base URL")
            sys.exit(1)

        service = CloudflareTempEmailAdapter(
            base_url=base_url,
            api_key=api_key,
            proxy=normalized_proxy,
            prefix=prefix,
            domain=domain,
            secret=secret,
            timeout=timeout,
        )
        service.service_type = EmailServiceType.CLOUDFLARE_TEMP_EMAIL
        return service

    # 默认使用 Skymail
    admin_email = config.get("skymail_admin_email", "")
    admin_password = config.get("skymail_admin_password", "")
    domains = config.get("skymail_domains", None)

    if not admin_email or not admin_password:
        print("错误: 未配置 Skymail 管理员账号")
        sys.exit(1)

    if not domains or not isinstance(domains, list) or len(domains) == 0:
        print("错误: 未配置 skymail_domains")
        sys.exit(1)

    service = SkymailClient(admin_email, admin_password, proxy=normalized_proxy, domains=domains)
    service.service_type = EmailServiceType.SKYMAIL

    print(f"正在生成 Skymail API Token (API: {service.api_base})...")
    print(f"可用域名: {', '.join(service.domains)}")
    token = service.generate_token()
    if not token:
        print("Token 生成失败，无法继续")
        sys.exit(1)

    return service
