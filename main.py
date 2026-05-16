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

players = [Player(0, "Alice", [Tag.WEREWOLF, Tag.ALIVE]),
           Player(1, "Bob", [Tag.WEREWOLF, Tag.ALIVE]),
           Player(2, "Test", [Tag.SEER, Tag.GOODPERSON, Tag.ALIVE])]

state = GameState(players)

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
async def websocket_endpoint(websocket: WebSocket, player_id: int):
    await manager.connect(player_id, websocket)
    try:
        while True:
            await state.get_new_message(player_id, await websocket.receive_text())
    except WebSocketDisconnect:
        manager.disconnect(player_id, websocket)
        await manager.broadcast(json.dumps({"type": "system", "msg": f"{player_id} exit the game"}))
