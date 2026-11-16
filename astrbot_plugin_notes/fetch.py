"""抓网页正文：只用标准库，带 SSRF 防护与编码兜底。"""

from __future__ import annotations

import gzip
import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import zlib

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_DROP_BLOCKS = re.compile(
    r"<(script|style|noscript|svg|iframe|head)[^>]*>.*?</\1>", re.I | re.S
)
_BREAKS = re.compile(r"</?(p|div|br|li|tr|h[1-6]|section|article)[^>]*>", re.I)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\u3000]+")
_BLANKS = re.compile(r"\n{3,}")
_META_CHARSET = re.compile(rb'charset=["\']?([a-zA-Z0-9_\-]+)', re.I)


def is_safe_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse((url or "").strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host in {"localhost", "127.0.0.1"}:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _decode(raw: bytes, content_type: str) -> str:
    charset = ""
    if "charset=" in (content_type or "").lower():
        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()
    if not charset:
        match = _META_CHARSET.search(raw[:4096])
        if match:
            charset = match.group(1).decode("ascii", "ignore")
    for enc in [charset, "utf-8", "gb18030", "latin-1"]:
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def html_to_text(page: str) -> str:
    page = _DROP_BLOCKS.sub(" ", page or "")
    page = _BREAKS.sub("\n", page)
    page = _TAGS.sub(" ", page)
    page = html.unescape(page)
    page = _SPACES.sub(" ", page)
    lines = [line.strip() for line in page.splitlines()]
    text = "\n".join(line for line in lines if line)
    return _BLANKS.sub("\n\n", text).strip()


def fetch_url_text(url: str, timeout: float = 20.0, max_chars: int = 6000) -> str:
    """同步抓取；调用方用 asyncio.to_thread 包一层。出错抛异常，由工具层兜。"""
    if not is_safe_url(url):
        raise ValueError("只允许公开的 http(s) 地址")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(3_000_000)
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
        content_type = resp.headers.get("Content-Type") or ""
    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    elif "deflate" in encoding:
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
    text = _decode(raw, content_type)
    if "html" in content_type.lower() or text.lstrip().startswith("<"):
        text = html_to_text(text)
    text = text.strip()
    if not text:
        raise ValueError("页面没有可读正文")
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + "\n…（已截断）"
    return text
