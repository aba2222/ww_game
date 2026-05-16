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
        self.current_stage = None
        self.last_night_killed = []
    
    def get_turn(self):
        return self.__turn
    
    def add_turn(self):
        self.__turn += 1
    
    def kill(self, id):
        self.__players[id].die()

    def get_player_tags(self, id):
        return self.__players[id].get_tags();

    def count_players_with_tags(self, tags):
        """计算同时拥有所有给定标签的玩家数量"""
        count = 0
        for i in range(self.pl_count):
            player_tags = self.get_player_tags(i)
            if all(tag in player_tags for tag in tags):
                count += 1
        return count

    def check(self):
        """检查胜负条件。返回 0 继续，1 好人胜，2 狼人胜"""
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
            return 2
        if not wolves_alive:
            logging.info("Good people won the game!")
            return 1
        return 0
    
    async def get_new_message(self, player_id : int, data : str):
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            logging.warning(f"Invalid JSON received from player {player_id}")
            return

        player_tags = self.get_player_tags(player_id)
        if Tag.ALIVE not in player_tags:
            logging.info(f"Dead player {player_id} attempted to send a message")
            return

        if msg["type"] == "chat":
            logging.info(f"{player_id}: {msg['msg']}")
            msg["player"] = player_id
            await manager.broadcast(json.dumps(msg))
        elif msg["type"] == "vote":
            if self.current_stage is None:
                logging.info(f"Player {player_id} attempted to vote when no stage is active")
                return
            
            allowed_tags = self.current_stage.who_can_talk()
            if not all(tag in player_tags for tag in allowed_tags):
                logging.info(f"Player {player_id} attempted to vote without proper tags for {self.current_stage.__name__}")
                return

            if self.vote[player_id] != -1:
                logging.info(f"{player_id} attempted to vote again")
                return
            logging.info(f"{player_id} voted {msg['target']}")
            self.vote[player_id] = msg["target"]
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
