import json

from constants import Tag
from player import manager

class GameState:
    def __init__(self, players):
        self.__turn = 1
        self.__players = players
        self.choose = None
    
    def get_turn(self):
        return self.__turn
    
    def add_turn(self):
        self.turn += 1
    
    def kill(self, id):
        self.__players[id].die()

    def get_player_tags(self, id):
        return self.__players[id].get_tags();

    def check(self):
        for player in self.__players:
            if Tag.GOODPERSON in player.get_tags():
                break
            print("Werewolves won the game!")
            return True
        
        for player in self.__players:
            if Tag.WEREWOLF in player.get_tags():
                break
            print("Good won the game!")
            return True
    
    async def get_new_message(self, player_name : str, data : str):
        msg = json.loads(data)
        if msg["type"] == "chat":
            msg["player"] = player_name
            await manager.broadcast(json.dumps(msg))
        elif msg["type"] == "choose":
            self.choose = msg["msg"]
    
    async def send_message(self, text, tag):
        for player in self.__players:
            if tag in player.get_tags():
                manager.send_personal_message(json.dumps({"type" : "chat", "player" : "System", "msg" : text}), player.id)
