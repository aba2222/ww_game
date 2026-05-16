# 狼人杀游戏项目 (Werewolf Game Project)

本项目是一个使用 Python、FastAPI 和 WebSockets 实现的实时多玩家“狼人杀”游戏。它通过异步游戏循环管理游戏状态、玩家角色和不同的游戏阶段（Stage）。

## 项目概述

游戏逻辑结构化为不同的阶段（例如：狼人阶段、预言家阶段、白天阶段）。玩家通过 WebSockets 与服务器交互，实现实时聊天和投票。

### 核心技术栈

- **FastAPI**: 用于 API 和 WebSocket 处理的 Web 框架。
- **Uvicorn**: 用于运行应用程序的 ASGI 服务器。
- **WebSockets**: 用于游戏事件和聊天的实时通信。
- **Python `asyncio`**: 用于游戏循环和并发任务的异步编程。

## 架构说明

- **`main.py`**: 应用程序入口点。设置 FastAPI 实例，定义 WebSocket 端点 (`/ws/{player_id}`)，并在应用生命周期内以后台任务启动 `game_main` 循环。
- **`game.py`**: 定义主游戏循环 (`game_main`)，它会按顺序循环执行游戏阶段列表。
- **`stage.py`**: 包含不同游戏阶段的逻辑。每个阶段继承自 `StageBase`，并实现自己的 `result` 逻辑以及该阶段的交互规则。
- **`state.py`**: 管理 `GameState`（游戏状态），包括玩家状态、回合追踪、投票结果和胜利条件检查。
- **`player.py`**: 定义 `Player` 类和 `ConnectionManager`，用于处理 WebSocket 连接和消息广播。
- **`constants.py`**: 包含 `Tag` 枚举，用于识别玩家角色（如 `WEREWOLF`, `SEER`, `VILLAGER`）和状态（如 `ALIVE`）。

## 构建与运行

### 前置条件

- Python 3.10+
- `pip`

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务器

```bash
uvicorn main:app --reload
```

服务器将启动在 `http://127.0.0.1:8000`。玩家可以通过 WebSocket 连接到 `ws://127.0.0.1:8000/ws/{player_id}`。

### 测试

目前没有自动化测试。
TODO: 实现游戏逻辑的单元测试和 WebSocket 通信的集成测试。

## 开发规范

- **异步逻辑**: 所有游戏循环和通信逻辑应保持使用 `async`/`await` 的异步模式。
- **基于标签的角色**: 使用 `constants.py` 中的 `Tag` 枚举来定义玩家属性。
- **阶段管理**: 要添加新的游戏阶段，请在 `stage.py` 中创建一个继承自 `StageBase` 的新类，并将其添加到 `game.py` 中的 `order` 列表。
- **日志**: 使用标准 `logging` 模块追踪游戏事件和调试状态。
