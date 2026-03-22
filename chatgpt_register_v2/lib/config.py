"""
配置加载模块
"""

import os
import json


def load_config():
    """从 config.json 加载配置，环境变量优先级更高"""
    config = {
        "total_accounts": 3,
        "concurrent_workers": 1,
        "mail_provider": "skymail",
        "mail_base_url": "",
        "mail_api_key": "",
        "mail_prefix": "",
        "mail_domain": "",
        "mail_secret": "",
        "mail_timeout": 30,
        "mail_expiry_time": 3600000,
        "skymail_admin_email": "",
        "skymail_admin_password": "",
        "skymail_domains": [],
        "gptmail_base_url": "https://mail.chatgpt.org.uk",
        "gptmail_api_key": "",
        "gptmail_prefix": "",
        "gptmail_domain": "",
        "gptmail_timeout": 30,
        "proxy": "",
        "output_file": "registered_accounts.txt",
        "accounts_file": "accounts.txt",
        "csv_file": "registered_accounts.csv",
        "enable_oauth": True,
        "oauth_required": True,
        "oauth_issuer": "https://auth.openai.com",
        "oauth_client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "oauth_redirect_uri": "http://localhost:1455/auth/callback",
        "ak_file": "ak.txt",
        "rk_file": "rk.txt",
        "token_json_dir": "tokens",
        "upload_api_url": "",
        "upload_api_token": "",
    }

    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"⚠️ 加载 config.json 失败: {e}")

    # 环境变量优先级更高
    env_mappings = {
        "MAIL_PROVIDER": "mail_provider",
        "MAIL_BASE_URL": "mail_base_url",
        "MAIL_API_KEY": "mail_api_key",
        "MAIL_PREFIX": "mail_prefix",
        "MAIL_DOMAIN": "mail_domain",
        "MAIL_SECRET": "mail_secret",
        "MAIL_TIMEOUT": "mail_timeout",
        "MAIL_EXPIRY_TIME": "mail_expiry_time",
        "SKYMAIL_ADMIN_EMAIL": "skymail_admin_email",
        "SKYMAIL_ADMIN_PASSWORD": "skymail_admin_password",
        "GPTMAIL_BASE_URL": "gptmail_base_url",
        "GPTMAIL_API_KEY": "gptmail_api_key",
        "GPTMAIL_PREFIX": "gptmail_prefix",
        "GPTMAIL_DOMAIN": "gptmail_domain",
        "GPTMAIL_TIMEOUT": "gptmail_timeout",
        "PROXY": "proxy",
        "TOTAL_ACCOUNTS": "total_accounts",
        "CONCURRENT_WORKERS": "concurrent_workers",
        "OUTPUT_FILE": "output_file",
        "ENABLE_OAUTH": "enable_oauth",
        "OAUTH_REQUIRED": "oauth_required",
        "OAUTH_ISSUER": "oauth_issuer",
        "OAUTH_CLIENT_ID": "oauth_client_id",
        "OAUTH_REDIRECT_URI": "oauth_redirect_uri",
        "AK_FILE": "ak_file",
        "RK_FILE": "rk_file",
        "TOKEN_JSON_DIR": "token_json_dir",
        "UPLOAD_API_URL": "upload_api_url",
        "UPLOAD_API_TOKEN": "upload_api_token",
    }

    for env_key, config_key in env_mappings.items():
        env_value = os.environ.get(env_key)
        if env_value is not None:
            if config_key in ["total_accounts", "concurrent_workers"]:
                config[config_key] = int(env_value)
            elif config_key in ["mail_timeout", "gptmail_timeout"]:
                config[config_key] = float(env_value)
            elif config_key in ["mail_expiry_time"]:
                config[config_key] = int(env_value)
            elif config_key in ["enable_oauth", "oauth_required"]:
                config[config_key] = env_value.lower() in ["1", "true", "yes", "y", "on"]
            else:
                config[config_key] = env_value

    return config


def as_bool(value):
    """将值转换为布尔值"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
