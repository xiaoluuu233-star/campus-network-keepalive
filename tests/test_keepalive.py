import pytest

from campus_keepalive import load_config


def test_load_config_requires_credentials(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("portal_base_url = 'http://172.32.253.17'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="userid"):
        load_config(path)
