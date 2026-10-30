# -*- coding: utf-8 -*-
"""
@Time    : 2025/12/10 23:26
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : LAN proxy bypass utility for accessing internal endpoints.
"""
import ipaddress
from urllib.parse import urlparse

import httpx
from openai import DefaultHttpxClient

# ======================== LAN Proxy Bypass Configuration ======================== #
# TUN mode (e.g., Clash-Meta) may intercept traffic to internal LAN endpoints.
# When LAZY_COMMIT_BYPASS_PROXY=true, LAN endpoints bypass system proxy for direct
# VPN access. Set via environment variable; defaults to False (no bypass).

# Carrier-grade NAT range, used by overlay VPNs such as Tailscale. Not covered by is_private.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _is_lan_endpoint(url: str) -> bool:
    """
    Check if a URL points to a private, loopback or VPN overlay IP address.

    Args:
        url: The URL to check

    Returns:
        True if the URL's host is such an address (or "localhost").
    """
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:  # a domain name
        return False
    return ip.is_private or ip.is_loopback or ip in _CGNAT_NETWORK


def get_lan_http_client(
    base_url: str, *, bypass_proxy: bool, timeout: httpx.Timeout | None = None, **kwargs
) -> httpx.Client | None:
    """
    Create a synchronous httpx.Client that bypasses the system proxy for LAN endpoints.

    When bypass_proxy is enabled and the base_url points to a LAN IP, the client bypasses
    system proxy (TUN mode). This ensures VPN connections to internal model endpoints are
    not intercepted by proxy software.

    Args:
        base_url: The API base URL to connect to.
        bypass_proxy: Value of LAZY_COMMIT_BYPASS_PROXY.
        timeout: Optional httpx.Timeout configuration.
        **kwargs: Additional arguments passed to httpx.Client.

    Returns:
        A configured client, or None to let the OpenAI SDK use its default client.

    Usage:
        http_client = get_lan_http_client(base_url, bypass_proxy=True)
        client = OpenAI(base_url=base_url, http_client=http_client, ...)
    """
    if not (bypass_proxy and _is_lan_endpoint(base_url)):
        return None

    # proxy=None + trust_env=False completely bypasses system proxy settings
    # This ensures direct connection via VPN interface, not intercepted by TUN
    if timeout is not None:
        kwargs["timeout"] = timeout
    # DefaultHttpxClient keeps the SDK's own defaults (connection limits, redirects, ...)
    return DefaultHttpxClient(proxy=None, trust_env=False, **kwargs)
