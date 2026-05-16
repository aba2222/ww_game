import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json

from constants import Tag
from game import game_main
from player import Player, manager
from state import GameState

import logging
logging.basicConfig(level=logging.DEBUG)

players = [Player(0, "Wolf", [Tag.WEREWOLF, Tag.ALIVE], "token_wolf"),
           Player(1, "Witch", [Tag.WITCH, Tag.GOD, Tag.GOODPERSON, Tag.ALIVE], "token_witch"),
           Player(2, "Seer", [Tag.SEER, Tag.GOD, Tag.GOODPERSON, Tag.ALIVE], "token_seer"),
           Player(3, "Villager", [Tag.VILLAGER, Tag.GOODPERSON, Tag.ALIVE], "token_villager")]

state = GameState(players)
manager.set_player_count(len(players))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(game_main(state))
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def game():
    return "TODO"

@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: int, token: str = None):
    # 身份验证逻辑
    if player_id < 0 or player_id >= len(players) or players[player_id].token != token:
        await websocket.accept() # 必须先 accept 才能关闭并发送状态码，或者直接拒绝握手
        await websocket.close(code=1008) # 1008: Policy Violation
        logging.warning(f"Authentication failed for player_id: {player_id}, token: {token}")
        return

    await manager.connect(player_id, websocket)
    
    # 连接成功后立即发送状态同步快照
    snapshot = state.get_snapshot(player_id)
    await manager.send_personal_message(json.dumps(snapshot), player_id)

    try:
        while True:
            await state.get_new_message(player_id, await websocket.receive_text())
    except WebSocketDisconnect:
        manager.disconnect(player_id, websocket)
        await manager.broadcast(json.dumps({"type": "system", "msg": f"{player_id} exit the game"}))
