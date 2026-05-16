import logging
import asyncio
from constants import Tag

from typing import List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    def set_player_count(self, count: int):
        self.active_connections = [None] * count

    async def connect(self, player_id: int, websocket: WebSocket):
        await websocket.accept()
        if player_id < len(self.active_connections):
            self.active_connections[player_id] = websocket
        else:
            logging.error(f"Player ID {player_id} out of bounds for connection manager")

    def disconnect(self, player_id: int, websocket: WebSocket):
        if player_id < len(self.active_connections) and self.active_connections[player_id] == websocket:
            self.active_connections[player_id] = None

    async def send_personal_message(self, message: str, id: int):
        if id < len(self.active_connections) and self.active_connections[id] is not None:
            try:
                await self.active_connections[id].send_text(message)
            except Exception as e:
                logging.error(f"Error sending personal message to {id}: {e}")

    async def broadcast(self, message: str):
        tasks = []
        for connection in self.active_connections:
            if connection is not None:
                tasks.append(connection.send_text(message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

manager = ConnectionManager()

class Player:
    def __init__(self, id, identity, tags, token):
        self.id = id
        self.__identity = identity
        self.__tags = tags
        self.token = token
    
    def die(self):
        if Tag.ALIVE in self.__tags:
            self.__tags.remove(Tag.ALIVE)
    
    def revive(self):
        if Tag.ALIVE not in self.__tags:
            self.__tags.append(Tag.ALIVE)
    
    def get_tags(self):
        return list(self.__tags)
