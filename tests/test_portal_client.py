from campus_keepalive import AppConfig
from portal_client import build_quickauth_params, extract_portal_params, response_diagnostic


def test_extract_portal_params():
    """验证 URL 编码的参数能被还原成普通字符串。"""
    url = "http://172.32.253.17/portal.do?wlanuserip=172.33.137.208&wlanacname=VBRAS-ZHKJ4&wlanacIp=172.32.253.8&mac=d0%3A89%3A21%3Aac%3A00%3A00&vlan=0"
    result = extract_portal_params(url)
    assert result["wlanuserip"] == "172.33.137.208"
    assert result["mac"] == "d0:89:21:ac:00:00"


def test_build_quickauth_params_generates_fresh_nonce():
    """每次认证都应生成新的时间戳和 UUID，避免复用旧请求。"""
    config = AppConfig(userid="test-user", password="secret")
    first = build_quickauth_params(config, {"wlanuserip": "172.33.137.208"})
    second = build_quickauth_params(config, {"wlanuserip": "172.33.137.208"})
    assert first["userid"] == "test-user"
    assert first["passwd"] == "secret"
    assert first["timestamp"].isdigit()
    assert first["uuid"] != second["uuid"]


def test_quickauth_params_do_not_add_group_id():
    """配置中的兼容字段不应被擅自发送为协议参数。"""
    config = AppConfig(userid="test-user", password="secret", groupId="2")
    params = build_quickauth_params(config, {})
    assert "groupId" not in params


def test_response_diagnostic_is_redacted_and_truncated():
    """诊断信息既要保留排错价值，也不能泄露密码或无限增长。"""
    class Response:
        status_code = 403
        headers = {"Content-Type": "application/json; charset=utf-8"}
        url = "http://portal/quickauth.do?userid=user&passwd=secret"
        text = '{"message":"' + ("x" * 500) + '"}'

    result = response_diagnostic(Response())

    assert result["status"] == 403
    assert result["content_type"] == "application/json; charset=utf-8"
    assert "secret" not in result["url"]
    assert len(result["body"]) <= 300
