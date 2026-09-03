import pytest

from campus_keepalive import load_config


def test_load_config_requires_credentials(tmp_path):
    """缺少 userid 时应尽早失败，而不是运行到网络请求才报错。"""
    path = tmp_path / "config.toml"
    path.write_text("portal_base_url = 'http://172.32.253.17'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="userid"):
        load_config(path)
