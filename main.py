import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json

from constants import Tag
from game import game_main
from player import Player, manager
from state import GameState

app = FastAPI()

players = [Player(0, "Alice", [Tag.WEREWOLF, Tag.ALIVE]),
           Player(1, "Bob", [Tag.WEREWOLF, Tag.ALIVE]),
           Player(2, "Test", [Tag.SEER, Tag.GOODPERSON, Tag.ALIVE])]


state = GameState(players)
asyncio.create_task(game_main(state))

@app.get("/")
async def game():
    return "TODO"

@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await manager.connect(websocket)
    try:
        while True:
            await state.get_new_message(player_name, await websocket.receive_text())
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type": "system", "msg": f"{player_name} exit the game"}))
