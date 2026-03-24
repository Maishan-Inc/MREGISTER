"""
常量定义 - 基于 codex-console-main 重构
"""

import random
from datetime import datetime
from enum import Enum
from typing import Dict, Tuple


class EmailServiceType(str, Enum):
    """邮箱服务类型"""
    SKYMAIL = "skymail"
    GPTMAIL = "gptmail"
    MOEMAIL = "moemail"
    CLOUDFLARE_TEMP_EMAIL = "cloudflare_temp_email"


class AccountStatus(str, Enum):
    """账户状态"""
    ACTIVE = "active"
    EXPIRED = "expired"
    BANNED = "banned"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_AUTH_URL = "https://auth.openai.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid email profile offline_access"

OPENAI_API_ENDPOINTS = {
    "sentinel": "https://sentinel.openai.com/backend-api/sentinel/req",
    "signup": "https://auth.openai.com/api/accounts/authorize/continue",
    "register": "https://auth.openai.com/api/accounts/user/register",
    "password_verify": "https://auth.openai.com/api/accounts/password/verify",
    "send_otp": "https://auth.openai.com/api/accounts/email-otp/send",
    "validate_otp": "https://auth.openai.com/api/accounts/email-otp/validate",
    "create_account": "https://auth.openai.com/api/accounts/create_account",
    "select_workspace": "https://auth.openai.com/api/accounts/workspace/select",
}

OPENAI_PAGE_TYPES = {
    "EMAIL_OTP_VERIFICATION": "email_otp_verification",
    "PASSWORD_REGISTRATION": "create_account_password",
    "LOGIN_PASSWORD": "login_password",
}

OTP_CODE_PATTERN = r"(?<!\d)(\d{6})(?!\d)"
OTP_MAX_ATTEMPTS = 40

PASSWORD_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DEFAULT_PASSWORD_LENGTH = 12

FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn",
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery", "Quinn", "Skyler",
    "Liam", "Noah", "Ethan", "Lucas", "Mason", "Oliver", "Elijah", "Aiden", "Henry", "Sebastian",
    "Grace", "Lily", "Chloe", "Zoey", "Nora", "Aria", "Hazel", "Aurora", "Stella", "Ivy"
]


def generate_random_user_info() -> dict:
    """
    生成随机用户信息

    Returns:
        包含 name 和 birthdate 的字典
    """
    name = random.choice(FIRST_NAMES)
    current_year = datetime.now().year
    birth_year = random.randint(current_year - 45, current_year - 18)
    birth_month = random.randint(1, 12)
    if birth_month in [1, 3, 5, 7, 8, 10, 12]:
        birth_day = random.randint(1, 31)
    elif birth_month in [4, 6, 9, 11]:
        birth_day = random.randint(1, 30)
    else:
        birth_day = random.randint(1, 28)
    birthdate = f"{birth_year}-{birth_month:02d}-{birth_day:02d}"
    return {
        "name": name,
        "birthdate": birthdate
    }


PROXY_TYPES = ["http", "socks5", "socks5h"]

DEFAULT_PROXY_CONFIG = {
    "enabled": False,
    "type": "http",
    "host": "127.0.0.1",
    "port": 7890,
}

ERROR_MESSAGES = {
    "DATABASE_ERROR": "数据库操作失败",
    "CONFIG_ERROR": "配置错误",
    "NETWORK_ERROR": "网络连接失败",
    "TIMEOUT": "操作超时",
    "VALIDATION_ERROR": "参数验证失败",
    "EMAIL_SERVICE_UNAVAILABLE": "邮箱服务不可用",
    "EMAIL_CREATION_FAILED": "创建邮箱失败",
    "OTP_NOT_RECEIVED": "未收到验证码",
    "OTP_INVALID": "验证码无效",
    "OPENAI_AUTH_FAILED": "OpenAI 认证失败",
    "OPENAI_RATE_LIMIT": "OpenAI 接口限流",
    "OPENAI_CAPTCHA": "遇到验证码",
    "PROXY_FAILED": "代理连接失败",
    "PROXY_AUTH_FAILED": "代理认证失败",
    "ACCOUNT_NOT_FOUND": "账户不存在",
    "ACCOUNT_ALREADY_EXISTS": "账户已存在",
    "ACCOUNT_INVALID": "账户无效",
    "TASK_NOT_FOUND": "任务不存在",
    "TASK_ALREADY_RUNNING": "任务已在运行中",
    "TASK_CANCELLED": "任务已取消",
}

REGEX_PATTERNS = {
    "EMAIL": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    "URL": r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+",
    "IP_ADDRESS": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "OTP_CODE": OTP_CODE_PATTERN,
}

TIME_CONSTANTS = {
    "SECOND": 1,
    "MINUTE": 60,
    "HOUR": 3600,
    "DAY": 86400,
    "WEEK": 604800,
}
