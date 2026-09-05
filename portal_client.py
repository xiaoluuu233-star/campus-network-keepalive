from __future__ import annotations

import logging
import time
import uuid
from typing import Mapping
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import requests

from campus_keepalive import AppConfig

LOGGER = logging.getLogger(__name__)
SENSITIVE = {"passwd", "password", "cookie", "jsessionid", "abms"}


def extract_portal_params(location: str) -> dict[str, str]:
    query = parse_qs(urlparse(location).query, keep_blank_values=True)
    return {key: values[-1] for key, values in query.items() if values}


def build_quickauth_params(config: AppConfig, discovered: Mapping[str, str]) -> dict[str, str]:
    values = {
        "userid": config.userid,
        "passwd": config.password,
        "wlanuserip": config.wlanuserip,
        "wlanacname": config.wlanacname,
        "wlanacIp": config.wlanacIp,
        "ssid": "",
        "vlan": config.vlan,
        "mac": config.mac,
        "version": "0",
        "portalpageid": "1",
        "timestamp": str(int(time.time() * 1000)),
        "uuid": str(uuid.uuid4()),
        "portaltype": "0",
        "bindCtrlId": "",
        "validateType": "0",
        "bindOperatorType": config.bindOperatorType,
        "sendFttrNotice": "0",
        "skipTemporaryAccountCheck": "false",
        "token3gpp": "",
        "noBindMac": "0",
        "roleGroupId": "",
        "roleClassId": "",
        "testGateWay": "",
        "skipOverTopLimit": "0",
    }
    for key in ("wlanuserip", "wlanacname", "wlanacIp", "mac", "vlan"):
        if discovered.get(key):
            values[key] = discovered[key]
    return values


def redact_params(params: Mapping[str, str]) -> dict[str, str]:
    return {key: ("***" if key.lower() in SENSITIVE else value) for key, value in params.items()}


def response_diagnostic(response: requests.Response) -> dict[str, object]:
    """Return bounded, credential-safe details for a Portal response."""
    parsed = urlparse(str(getattr(response, "url", "")))
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, "***" if key.lower() in SENSITIVE else value))
    safe_url = urlunparse(parsed._replace(query=urlencode(query)))
    body = " ".join(str(getattr(response, "text", "" )).split())[:300]
    return {
        "status": int(getattr(response, "status_code", 0)),
        "content_type": str(getattr(response, "headers", {}).get("Content-Type", "")),
        "url": safe_url,
        "body": body,
    }


class PortalClient:
    def __init__(self, config: AppConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()
        self.discovered: dict[str, str] = {}

    def check_online(self) -> bool:
        try:
            response = self.session.get(self.config.connectivity_url, timeout=self.config.timeout, allow_redirects=False)
            if response.is_redirect or response.is_permanent_redirect:
                return False
            return response.status_code == 200 and "Microsoft Connect Test" in response.text
        except requests.RequestException:
            return False

    def discover_params(self) -> dict[str, str]:
        response = self.session.get(self.config.connectivity_url, timeout=self.config.timeout, allow_redirects=False)
        location = response.headers.get("Location", "")
        self.discovered = extract_portal_params(location) if location else {}
        return self.discovered

    def login(self) -> bool:
        try:
            discovered = self.discover_params()
        except requests.RequestException as exc:
            LOGGER.warning("无法获取 Portal 参数: %s", exc)
            discovered = self.discovered
        params = build_quickauth_params(self.config, discovered)
        LOGGER.info(
            "发起 Portal 认证: userid=%s, wlanuserip=%s, wlanacname=%s",
            params["userid"],
            params["wlanuserip"],
            params["wlanacname"],
        )
        try:
            response = self.session.get(
                f"{self.config.portal_base_url.rstrip('/')}/quickauth.do",
                params=params,
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{self.config.portal_base_url.rstrip('/')}/portal.do",
                },
                timeout=self.config.timeout,
            )
            diagnostic = response_diagnostic(response)
            LOGGER.info(
                "Portal 返回: status=%s, content_type=%s, url=%s, body=%s",
                diagnostic["status"],
                diagnostic["content_type"] or "(none)",
                diagnostic["url"] or "(none)",
                diagnostic["body"] or "(empty)",
            )
            body = response.text.lower()
            return response.ok and any(token in body for token in ("认证成功", "success", "成功", "already online"))
        except requests.RequestException as exc:
            LOGGER.warning("Portal 认证请求失败: %s", exc)
            return False

    def heartbeat(self) -> bool:
        try:
            response = self.session.get(self.config.connectivity_url, timeout=self.config.timeout, allow_redirects=False)
            return response.status_code == 200 and "Microsoft Connect Test" in response.text
        except requests.RequestException:
            return False
