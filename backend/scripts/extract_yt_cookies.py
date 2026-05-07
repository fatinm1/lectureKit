#!/usr/bin/env python3
"""
Extract a minimal Netscape-format cookies.txt for YouTube from the local Chrome profile.

Use locally (not on Railway) to build a small cookie file for YTDLP_COOKIE_FILE:
  python scripts/extract_yt_cookies.py > minimal_cookies.txt
Then optionally base64-encode that output for a compact secret if your host limits size.
"""

from __future__ import annotations

import sys
import time

IMPORTANT_KEYS = frozenset(
    {
        "CONSENT",
        "VISITOR_INFO1_LIVE",
        "YSC",
        "LOGIN_INFO",
        "HSID",
        "SSID",
        "APISID",
        "SAPISID",
        "__Secure-1PAPISID",
        "__Secure-3PAPISID",
    }
)


def extract_minimal_youtube_cookies() -> str | None:
    try:
        import browser_cookie3
    except ImportError:
        print(
            "Error: install browser-cookie3 (pip install browser-cookie3).",
            file=sys.stderr,
        )
        return None

    try:
        cookies = browser_cookie3.chrome()
    except Exception as e:
        print(f"Error reading Chrome cookies: {e}", file=sys.stderr)
        return None

    lines: list[str] = ["# Netscape HTTP Cookie File"]
    now = int(time.time())

    for cookie in cookies:
        dom = (cookie.domain or "").lower()
        if "youtube.com" not in dom:
            continue
        if cookie.name not in IMPORTANT_KEYS:
            continue

        domain = cookie.domain or ".youtube.com"
        include_subdomain = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.path or "/"
        secure = "TRUE" if getattr(cookie, "secure", False) else "FALSE"
        expires = cookie.expires
        exp_int = int(expires) if expires else now + 86400 * 365

        lines.append(
            f"{domain}\t{include_subdomain}\t{path}\t{secure}\t{exp_int}\t{cookie.name}\t{cookie.value}"
        )

    if len(lines) <= 1:
        print("No matching YouTube cookies found in Chrome.", file=sys.stderr)
        return None

    return "\n".join(lines)


if __name__ == "__main__":
    out = extract_minimal_youtube_cookies()
    if out:
        print(out)
    else:
        sys.exit(1)
