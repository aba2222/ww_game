from constants import Tag

from typing import List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, id: int):
        await self.active_connections[id].send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

class Player:
    def __init__(self, id, identity, tags):
        self.id = id
        self.__identity = identity
        self.__tags = tags
    
    def die(self):
        if Tag.ALIVE in self.__tags:
            self.__tags.remove(Tag.ALIVE)
    
    def get_tags(self):
        return self.__tags
