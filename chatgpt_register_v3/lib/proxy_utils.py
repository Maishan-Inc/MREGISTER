"""
代理工具模块 - 支持带认证凭证的 SOCKS5 代理
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_proxy_url(proxy: object) -> str:
    """
    标准化代理 URL

    - 保留空值
    - 保留 netloc 中的认证凭证
    - 将 socks5:// 升级为 socks5h:// 以通过代理解析 DNS

    Args:
        proxy: 代理 URL 对象

    Returns:
        标准化后的代理 URL
    """
    text = str(proxy or "").strip()
    if not text:
        return ""

    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        return text

    scheme = parts.scheme.lower()
    if scheme == "socks5":
        scheme = "socks5h"

    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def parse_proxy_url(proxy_url: str) -> dict:
    """
    解析代理 URL 为组件字典

    Args:
        proxy_url: 代理 URL

    Returns:
        包含代理组件的字典
    """
    normalized = normalize_proxy_url(proxy_url)
    if not normalized:
        return {}

    parts = urlsplit(normalized)
    result = {
        "scheme": parts.scheme,
        "host": parts.hostname or "",
        "port": parts.port or 1080,
        "username": parts.username or None,
        "password": parts.password or None,
    }

    return result


def build_proxy_dict(proxy_url: str) -> dict:
    """
    构建请求库使用的代理字典

    Args:
        proxy_url: 代理 URL

    Returns:
        代理字典，如 {"http": "...", "https": "..."}
    """
    normalized = normalize_proxy_url(proxy_url)
    if not normalized:
        return {}

    return {
        "http": normalized,
        "https": normalized,
    }
