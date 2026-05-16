import asyncio
import json
import logging

from constants import Tag
from player import manager

class GameState:
    def __init__(self, players):
        self.__turn = 1
        self.__players = players
        self.vote = [-1] * len(players)
        self.voted_player = 0
        self.pl_count = len(players)
    
    def get_turn(self):
        return self.__turn
    
    def add_turn(self):
        self.__turn += 1
    
    def kill(self, id):
        self.__players[id].die()

    def get_player_tags(self, id):
        return self.__players[id].get_tags();

    def check(self):
        wolves_alive = False
        good_alive = False
        for i in range(self.pl_count):
            tags = self.get_player_tags(i)
            if Tag.ALIVE not in tags:
                continue
            if Tag.WEREWOLF in tags:
                wolves_alive = True
            elif Tag.GOODPERSON in tags:
                good_alive = True
        
        if not good_alive:
            logging.info("Werewolves won the game!")
            return True
        if not wolves_alive:
            logging.info("Good people won the game!")
            return True
        return False
    
    async def get_new_message(self, player_id : int, data : str):
        msg = json.loads(data)
        if msg["type"] == "chat":
            logging.info(f"{player_id}: {msg['msg']}")
            msg["player"] = player_id
            await manager.broadcast(json.dumps(msg))
        elif msg["type"] == "vote":
            logging.info(f"{player_id} voted {msg['target']}")
            self.vote[int(msg["player"])] = msg["target"]
            self.voted_player += 1

    async def send_message(self, text, tags):
        tasks = []
        for i in range(self.pl_count):
            player_tags = self.get_player_tags(i)
            if not all(tag in player_tags for tag in tags):
                continue
            msg = json.dumps({"type": "chat", "player": "System", "msg": text})
            logging.debug(f"Sending message to {self.__players[i].id}: {text}")
            tasks.append(manager.send_personal_message(msg, self.__players[i].id))
        if tasks:
            await asyncio.gather(*tasks)
