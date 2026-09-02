from campus_keepalive import AppConfig
from portal_client import build_quickauth_params, extract_portal_params


def test_extract_portal_params():
    url = "http://172.32.253.17/portal.do?wlanuserip=172.33.137.208&wlanacname=VBRAS-ZHKJ4&wlanacIp=172.32.253.8&mac=d0%3A89%3A21%3Aac%3A00%3A00&vlan=0"
    result = extract_portal_params(url)
    assert result["wlanuserip"] == "172.33.137.208"
    assert result["mac"] == "d0:89:21:ac:00:00"


def test_build_quickauth_params_generates_fresh_nonce():
    config = AppConfig(userid="test-user", password="secret")
    first = build_quickauth_params(config, {"wlanuserip": "172.33.137.208"})
    second = build_quickauth_params(config, {"wlanuserip": "172.33.137.208"})
    assert first["userid"] == "test-user"
    assert first["passwd"] == "secret"
    assert first["timestamp"].isdigit()
    assert first["uuid"] != second["uuid"]
