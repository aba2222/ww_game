# 狼人杀项目 Bug 及改进建议汇总

以下是根据代码深度分析整理出的 Bug 报告和改进建议，已按严重程度排序，建议提交至 [GitHub Issues](https://github.com/aba2222/ww_game/issues)。

---

## 1. [Bug] 广播逻辑在玩家未满时会导致程序崩溃
**严重程度：** 紧急 (Critical)
**描述：** 
在 `player.py` 的 `broadcast` 方法中，程序直接遍历 `self.active_connections` 并调用 `send_text`。
```python
async def broadcast(self, message: str):
    for connection in self.active_connections:
        await connection.send_text(message)
```
由于 `active_connections` 初始化为 `[None] * 3`，只要有位置没有玩家连接，程序就会抛出 `AttributeError: 'NoneType' object has no attribute 'send_text'` 异常，导致 WebSocket 连接中断。

**建议修复：**
在发送前增加空值检查：
```python
async def broadcast(self, message: str):
    for connection in self.active_connections:
        if connection:
            await connection.send_text(message)
```

---

## 2. [Bug] 投票环节无投票记录时会导致 ValueError 崩溃
**严重程度：** 紧急 (Critical)
**描述：** 
在 `stage.py` 的 `wait_vote` 函数中，如果没有任何玩家投票（例如超时或异常情况），`vote_count` 将为空。此时调用 `max(vote_count.values())` 会触发 `ValueError: max() arg is an empty sequence`。

**建议修复：**
在计算最大票数前检查 `vote_count` 是否为空：
```python
if not vote_count:
    return -1
max_votes = max(vote_count.values())
```

---

## 3. [Bug] 恶意客户端可通过重复投票绕过人数限制
**严重程度：** 高 (High)
**描述：** 
`GameState.get_new_message` 处理投票消息时，仅仅是自增 `voted_player` 计数器：
```python
elif msg["type"] == "vote":
    self.vote[player_id] = msg["target"]
    self.voted_player += 1
```
同一玩家可以发送多次投票消息，导致 `voted_player` 迅速达到 `voter_number`，从而强制结束投票环节，且最后一次投票会覆盖之前的投票。

**建议修复：**
记录已投票的玩家列表，或检查 `self.vote[player_id]` 是否已经设置过（不为 -1）。

---

## 4. [Bug] 解析无效 JSON 导致 WebSocket 异常断开
**严重程度：** 中 (Medium)
**描述：** 
`state.py` 中的 `get_new_message` 直接调用 `json.loads(data)`。如果前端或恶意用户发送了格式错误的字符串，会抛出 `json.JSONDecodeError`。由于该函数在 `main.py` 的 `while True` 循环中被调用，未捕获的异常会导致该玩家的 WebSocket 连接直接关闭。

**建议修复：**
使用 `try-except` 包裹 JSON 解析过程，并在出错时向客户端返回错误提示或直接忽略。

---

## 5. [Logic] 缺乏权限校验：死亡玩家或非权限角色可干扰游戏
**严重程度：** 中 (Medium)
**描述：** 
目前的 `get_new_message` 没有任何权限检查。
1. **死者发言/投票**：拥有 `Tag.ALIVE` 以外标签的玩家依然可以发送消息并被系统广播或计票。
2. **跨阶段干扰**：平民可以在狼人阶段发送投票消息，虽然系统不提示，但会干扰 `voted_player` 计数。

**建议意见：**
在 `GameState` 中维护一个 `current_stage` 状态，并在处理消息时校验玩家的 `Tag` 是否符合当前阶段的 `who_can_talk()` 要求。

---

## 6. [Suggestion] 架构改进建议
**内容：**
1. **硬编码解耦**：将玩家上限 `3` 改为配置参数或根据 `players` 列表长度动态初始化 `ConnectionManager`。
2. **异步性能优化**：当前的广播是顺序 `await`，建议使用 `asyncio.gather` 并发发送，防止单个连接延迟阻塞全场。
3. **游戏结束即时检查**：目前的胜负判定主要在白天阶段。建议在每个玩家死亡时（`kill` 方法中）立即触发胜负判定，若达成条件则直接终止游戏循环。
4. **状态持久化与多房间支持**：目前使用全局变量，建议重构为支持多房间模式，每个房间拥有独立的 `GameState` 实例。
