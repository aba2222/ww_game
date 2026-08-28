import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import json

from constants import Tag
from game import game_main
from player import Player, manager
from state import GameState

import logging
logging.basicConfig(level=logging.INFO)

<<<<<<< Updated upstream
players = [Player(0, "Alice", [Tag.WEREWOLF, Tag.ALIVE]),
           Player(1, "Bob", [Tag.WEREWOLF, Tag.ALIVE]),
           Player(2, "Test", [Tag.SEER, Tag.GOODPERSON, Tag.ALIVE])]

state = GameState(players)
=======
import random
roles = [
    ("Wolf", [Tag.WEREWOLF, Tag.ALIVE]),
    ("WolfKing", [Tag.WOLFKING, Tag.ALIVE]),
#    ("Witch", [Tag.WITCH, Tag.GOD, Tag.GOODPERSON, Tag.ALIVE]),
    ("Seer", [Tag.SEER, Tag.GOD, Tag.GOODPERSON, Tag.ALIVE]),
#    ("Hunter", [Tag.HUNTER, Tag.GOD, Tag.GOODPERSON, Tag.ALIVE]),
    ("Guard", [Tag.GUARD, Tag.GOD, Tag.GOODPERSON, Tag.ALIVE]),
    ("Villager", [Tag.VILLAGER, Tag.GOODPERSON, Tag.ALIVE]),
    ("Villager", [Tag.VILLAGER, Tag.GOODPERSON, Tag.ALIVE]),
]

def create_players(role_list):
    random.shuffle(role_list)

    players = []

    for player_id, (name, tags) in enumerate(role_list):
        players.append(
            Player(
                player_id,
                name,
                tags,
                f"token_{player_id}"
            )
        )

    return players

players = create_players(roles)

state = GameState(players)
manager.set_player_count(len(players))
game_start_event = asyncio.Event()

async def wait_for_game_start():
    await game_start_event.wait()
    await game_main(state)
>>>>>>> Stashed changes

@asynccontextmanager
async def lifespan(app: FastAPI):
    game_task = asyncio.create_task(wait_for_game_start())
    yield
    game_task.cancel()

app = FastAPI(lifespan=lifespan)

@app.post("/start")
async def start_game():
    game_start_event.set()
    return {"status": "started"}

@app.get("/")
async def game():
    template_path = Path(__file__).resolve().parent / "templates" / "game.html"
    return FileResponse(template_path)

@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: int):
    await manager.connect(player_id, websocket)
    try:
        while True:
            await state.get_new_message(player_id, await websocket.receive_text())
    except WebSocketDisconnect:
        await manager.broadcast(json.dumps({"type": "system", "msg": f"{player_id} exit the game"}))
    finally:
        manager.disconnect(player_id, websocket)
