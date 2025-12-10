# -*- coding: utf-8 -*-
"""
@Time    : 2025/12/10 23:26
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : LAN proxy bypass utility for accessing internal endpoints.
"""
from urllib.parse import urlparse

import httpx

from smart_commit.settings import settings


# ======================== LAN Proxy Bypass Configuration ======================== #
# TUN mode (e.g., Clash-Meta) may intercept traffic to internal LAN endpoints.
# When LAZY_COMMIT_BYPASS_PROXY=true, LAN endpoints bypass system proxy for direct
# VPN access. Set via environment variable; defaults to False (no bypass).

# Private IP ranges (RFC 1918) - commonly used for internal networks
_PRIVATE_IP_PREFIXES = (
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
)


def _is_lan_endpoint(url: str) -> bool:
    """
    Check if a URL points to a private LAN IP address.

    Args:
        url: The URL to check

    Returns:
        True if the URL's host is a private IP address.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return host.startswith(_PRIVATE_IP_PREFIXES) or host == "localhost"
    except Exception:
        return False


def get_lan_http_client(
    base_url: str, *, timeout: httpx.Timeout | None = None, **kwargs
) -> httpx.Client:
    """
    Create a synchronous httpx.Client configured for LAN endpoints.

    When LAZY_COMMIT_BYPASS_PROXY=true and the base_url points to a LAN IP,
    the client bypasses system proxy (TUN mode). This ensures VPN connections
    to internal model endpoints are not intercepted by proxy software.

    By default (LAZY_COMMIT_BYPASS_PROXY=false), uses standard httpx behavior.

    Args:
        base_url: The API base URL to connect to.
        timeout: Optional httpx.Timeout configuration.
        **kwargs: Additional arguments passed to httpx.Client.

    Returns:
        Configured httpx.Client instance.

    Usage:
        # Set LAZY_COMMIT_BYPASS_PROXY=true in environment, then:
        http_client = get_lan_http_client_sync(base_url, timeout=timeout)
        client = OpenAI(base_url=base_url, http_client=http_client, ...)
    """
    # Only bypass proxy when explicitly enabled via environment variable
    if settings.LAZY_COMMIT_BYPASS_PROXY and _is_lan_endpoint(base_url):
        # proxy=None + trust_env=False completely bypasses system proxy settings
        # This ensures direct connection via VPN interface, not intercepted by TUN
        return httpx.Client(timeout=timeout, proxy=None, trust_env=False, **kwargs)

    # Default behavior: use system proxy settings
    return httpx.Client(timeout=timeout, **kwargs)
