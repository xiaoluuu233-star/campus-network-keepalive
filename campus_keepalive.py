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
    """程序运行所需的全部配置。

    使用不可变数据类的好处是：配置加载完成后不会被运行循环意外改写，
    每个字段也能通过类型和默认值直接看懂用途。
    """

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
    """从 TOML 文件读取配置，并检查账号密码是否存在。"""
    # 以二进制模式打开是 tomllib.load() 的标准用法；它负责解析 TOML。
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    # 去掉账号两端空格，但密码不 strip，避免意外改变合法密码。
    userid = str(raw.get("userid", "")).strip()
    password = str(raw.get("password", ""))
    if not userid:
        raise ValueError("userid is required")
    if not password:
        raise ValueError("password is required")
    # 只取 AppConfig 已声明的字段，防止配置文件中的拼写错误字段
    # 被悄悄传给构造函数或影响程序行为。
    values = {k: raw[k] for k in AppConfig.__dataclass_fields__ if k in raw}
    values["userid"], values["password"] = userid, password
    return AppConfig(**values)


def configure_logging(path: Path) -> None:
    """同时把日志输出到终端和文件，便于首次运行观察状态。"""
    # mkdir 的 parents=True 允许用户把日志放在尚不存在的子目录中。
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")])


def run_forever(config: AppConfig, client, stop_event: threading.Event | None = None) -> None:
    """持续检测网络；掉线时认证，在线时按间隔发送心跳。

    stop_event 用于测试和优雅退出。Event.wait() 既能等待指定秒数，
    也能在收到停止信号时立即返回，比 time.sleep() 更容易中断。
    """
    stop_event = stop_event or threading.Event()
    # 单调时钟不受系统时间被校准影响，适合计算时间间隔。
    last_heartbeat = 0.0
    # 认证失败后逐步延长等待时间，避免持续请求 Portal。
    backoff = 5.0
    logger = logging.getLogger(__name__)
    while not stop_event.is_set():
        try:
            # 先访问联网检测地址，判断当前是否已经能正常出网。
            online = client.check_online()
            now = time.monotonic()
            if not online:
                logger.warning("检测到掉线，开始重新认证")
                # login() 内部会重新发现 Portal 参数并发起认证请求。
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
                # 只有达到心跳间隔才请求，避免每轮检测都产生网络流量。
                if client.heartbeat():
                    logger.info("心跳成功")
                    last_heartbeat = now
                else:
                    logger.warning("心跳失败，下一轮重新检查")
            # 正常状态按检测间隔继续下一轮。
            stop_event.wait(config.check_interval)
        except Exception:
            # 单轮异常不应让整个保活程序退出；记录堆栈后稍后重试。
            logger.exception("运行循环出现异常")
            stop_event.wait(backoff)


def main() -> None:
    """命令行入口：解析参数、加载配置并启动客户端。"""
    parser = argparse.ArgumentParser(description="校园网自动登录与保活")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()
    config = load_config(args.config)
    configure_logging(Path(config.log_path))
    # 延迟导入让配置校验先发生，也减少仅导入本模块时的副作用。
    from portal_client import PortalClient
    run_forever(config, PortalClient(config))


if __name__ == "__main__":
    main()
