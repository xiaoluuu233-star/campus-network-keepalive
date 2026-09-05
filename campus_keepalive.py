from __future__ import annotations

import argparse
import logging
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    userid: str
    password: str
    portal_base_url: str = "http://172.32.253.17"
    connectivity_url: str = "http://www.msftconnecttest.com/connecttest.txt"
    check_interval: int = 30
    heartbeat_interval: int = 60
    timeout: float = 8.0
    max_retries: int = 5
    log_path: str = "campus_keepalive.log"
    wlanuserip: str = ""
    wlanacname: str = "VBRAS-ZHKJ4"
    wlanacIp: str = "172.32.253.8"
    mac: str = ""
    vlan: str = "0"
    groupId: str = "2"
    bindOperatorType: str = "2"


def load_config(path: Path) -> AppConfig:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    userid = str(raw.get("userid", "")).strip()
    password = str(raw.get("password", ""))
    if not userid:
        raise ValueError("userid is required")
    if not password:
        raise ValueError("password is required")
    values = {k: raw[k] for k in AppConfig.__dataclass_fields__ if k in raw}
    values["userid"], values["password"] = userid, password
    return AppConfig(**values)


def configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")])


def run_forever(config: AppConfig, client, stop_event: threading.Event | None = None) -> None:
    stop_event = stop_event or threading.Event()
    last_heartbeat = 0.0
    backoff = 5.0
    logger = logging.getLogger(__name__)
    while not stop_event.is_set():
        try:
            online = client.check_online()
            now = time.monotonic()
            if not online:
                logger.warning("检测到掉线，开始重新认证")
                if client.login():
                    logger.info("重新认证成功")
                    backoff = 5.0
                    last_heartbeat = now
                else:
                    logger.error("认证失败，将在 %.0f 秒后重试", backoff)
                    stop_event.wait(backoff)
                    backoff = min(backoff * 2, max(30.0, config.check_interval * config.max_retries))
                    continue
            elif now - last_heartbeat >= config.heartbeat_interval:
                if client.heartbeat():
                    logger.info("心跳成功")
                    last_heartbeat = now
                else:
                    logger.warning("心跳失败，下一轮重新检查")
            stop_event.wait(config.check_interval)
        except Exception:
            logger.exception("运行循环出现异常")
            stop_event.wait(backoff)


def main() -> None:
    parser = argparse.ArgumentParser(description="校园网自动登录与保活")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--no-tray", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    configure_logging(Path(config.log_path))
    from portal_client import PortalClient
    if args.no_tray:
        run_forever(config, PortalClient(config))
    else:
        from tray_app import TrayApplication
        TrayApplication(config, args.config, background=args.background).run()


if __name__ == "__main__":
    main()



