# 校园网自动登录防掉线

## 本地运行

1. 安装 Python 3.11 或更高版本。
2. 复制 `config.example.toml` 为 `config.toml`，填入账号和密码。
3. 安装依赖：`python -m pip install -r requirements.txt`。
4. 运行：`python campus_keepalive.py --config config.toml`。

首次运行建议保持终端打开，确认日志中的认证和心跳状态。`config.toml` 已被 Git 忽略，不要提交它。

## GitHub Actions

推送到私有仓库后，Actions 会运行测试并构建 `campus-network-keepalive.exe`。在对应 workflow 的 Artifacts 下载即可。构建产物不包含账号密码；运行 exe 时仍需在同目录准备本地 `config.toml`。

## VS Code

在 VS Code 中打开本目录，复制配置模板并按上面的命令运行。可使用集成终端查看日志。
