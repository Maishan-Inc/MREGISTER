from urllib.parse import urlsplit, urlunsplit


def normalize_proxy_url(proxy):
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
