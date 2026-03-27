# CLIProxyAPI-B

一个独立运行的 pool-maintainer，用来围绕本地 `cli-proxy-api`/CPA 部署做库存扫描、健康判定、补池触发和 Web UI 展示。

## 功能

- 读取本地 auths 目录并结合 CLIProxyAPI 管理接口做库存扫描
- 根据 token 存在性、管理接口健康、usage 阈值做基础健康判定
- 保存状态和历史事件到本地 `data/`
- 提供 Web UI、状态 API、手动扫描、手动补池入口
- 可选自动扫描、自动补池

## 依赖

- Python 3.11+
- 推荐 `uv`

## 启动

```bash
cd /home/claw/projects/cli-proxy-api-B
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8420 --reload
```

打开：`http://127.0.0.1:8420`

## 关键环境变量

- `CLIPROXY_BASE_URL`：默认 `http://127.0.0.1:8317`
- `CLIPROXY_MANAGEMENT_KEY`：CLIProxyAPI 管理 key
- `CLIPROXY_AUTH_DIR`：默认 `/home/claw/projects/cli-proxy-api/auths`
- `POOL_MIN_HEALTHY_COUNT`：最低健康库存
- `POOL_TARGET_HEALTHY_COUNT`：补池目标库存
- `POOL_AUTO_SCAN_ENABLED`：是否自动扫描，默认 `true`
- `POOL_AUTO_REPLENISH_ENABLED`：是否自动补池，默认 `false`
- `POOL_REPLENISH_COMMAND`：补池执行命令，支持 `{count}` 占位符

示例：

```bash
export CLIPROXY_MANAGEMENT_KEY="your-management-key"
export POOL_AUTO_REPLENISH_ENABLED=true
export POOL_REPLENISH_COMMAND='cd /home/claw/projects/register/openai-register && source venv/bin/activate && python openai_register.py --once --cpa-upload'
```

如果你想把请求数量传给外部脚本，可以把命令写成：

```bash
export POOL_REPLENISH_COMMAND='bash /path/to/replenish.sh {count}'
```

## API

- `GET /api/status`
- `GET /api/history?limit=50`
- `POST /api/scan`
- `POST /api/replenish?count=10`

## 当前设计取舍

- 第一版不直接物理删除坏号，只做健康判定和补池控制
- 第一版补池通过外部命令执行，尽量不侵入注册机项目
- 健康判定以 CPA 库存为中心，但比 CLIProxyAPI 原生状态更谨慎
