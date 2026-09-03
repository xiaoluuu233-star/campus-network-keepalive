from __future__ import annotations

import logging
import time
import uuid
from typing import Mapping
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import requests

from campus_keepalive import AppConfig

LOGGER = logging.getLogger(__name__)
# 这些字段可能包含密码、会话标识或认证上下文，写日志前必须遮盖。
SENSITIVE = {"passwd", "password", "cookie", "jsessionid", "abms"}


def extract_portal_params(location: str) -> dict[str, str]:
    """从 Portal 重定向地址提取查询参数。

    parse_qs 会正确处理 URL 编码，并把重复参数表示成列表；这里取最后
    一个值，保持与 Portal 常见参数格式兼容。
    """
    query = parse_qs(urlparse(location).query, keep_blank_values=True)
    return {key: values[-1] for key, values in query.items() if values}


def build_quickauth_params(config: AppConfig, discovered: Mapping[str, str]) -> dict[str, str]:
    """组合 quickauth.do 所需参数，并用最新发现值覆盖配置回退值。"""
    # timestamp 和 uuid 必须每次登录重新生成，不能在配置加载时固定。
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
    # 重定向中的动态网络信息比本地配置更准确；空值不覆盖已有回退值。
    for key in ("wlanuserip", "wlanacname", "wlanacIp", "mac", "vlan"):
        if discovered.get(key):
            values[key] = discovered[key]
    return values


def redact_params(params: Mapping[str, str]) -> dict[str, str]:
    """返回可记录到日志的参数副本，不修改调用方传入的字典。"""
    return {key: ("***" if key.lower() in SENSITIVE else value) for key, value in params.items()}


def response_diagnostic(response: requests.Response) -> dict[str, object]:
    """Return bounded, credential-safe details for a Portal response."""
    # 即使 requests 已经跟随重定向，也只记录经过脱敏和长度限制的信息。
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
    """封装联网检测、Portal 参数发现、认证和心跳请求。"""

    def __init__(self, config: AppConfig, session: requests.Session | None = None):
        # 注入 session 方便单元测试使用假的 HTTP 会话，也便于复用连接。
        self.config = config
        self.session = session or requests.Session()
        self.discovered: dict[str, str] = {}

    def check_online(self) -> bool:
        """访问联网检测地址，只有返回微软测试文本才视为在线。"""
        try:
            response = self.session.get(self.config.connectivity_url, timeout=self.config.timeout, allow_redirects=False)
            # 被重定向通常说明请求被 Portal 截获，需要进入认证流程。
            if response.is_redirect or response.is_permanent_redirect:
                return False
            return response.status_code == 200 and "Microsoft Connect Test" in response.text
        except requests.RequestException:
            return False

    def discover_params(self) -> dict[str, str]:
        """请求联网检测地址，并从 Portal 重定向中提取动态参数。"""
        response = self.session.get(self.config.connectivity_url, timeout=self.config.timeout, allow_redirects=False)
        location = response.headers.get("Location", "")
        self.discovered = extract_portal_params(location) if location else {}
        return self.discovered

    def login(self) -> bool:
        """发现参数后调用 quickauth.do，并根据响应判断认证结果。"""
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
            # 只依据响应状态和已知成功文字判断，避免把任意 200 当成成功。
            body = response.text.lower()
            return response.ok and any(token in body for token in ("认证成功", "success", "成功", "already online"))
        except requests.RequestException as exc:
            LOGGER.warning("Portal 认证请求失败: %s", exc)
            return False

    def heartbeat(self) -> bool:
        """发送轻量联网检测请求，确认认证状态仍然有效。"""
        try:
            response = self.session.get(self.config.connectivity_url, timeout=self.config.timeout, allow_redirects=False)
            return response.status_code == 200 and "Microsoft Connect Test" in response.text
        except requests.RequestException:
            return False
