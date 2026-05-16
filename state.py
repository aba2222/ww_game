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
        self.message_history = []
        self.witch_save_used = False
        self.witch_kill_used = False
        self.night_actions = {
            "wolf_kill": -1,
            "witch_save": -1,
            "witch_kill": -1,
        }
        self.players_with_testament = [] # 记录有遗言权的死者ID
        self.current_speaker = -1 # 当前发言者ID，-1表示自由发言或非发言阶段

    def reset_night_actions(self):
        """重置夜晚行动记录"""
        self.night_actions = {
            "wolf_kill": -1,
            "witch_save": -1,
            "witch_kill": -1
        }

    def settle_night(self):
        """结算夜晚的所有行动，计算最终死亡名单"""
        killed_this_night = set()
        
        wolf_target = self.night_actions["wolf_kill"]
        witch_save = self.night_actions["witch_save"]
        witch_kill = self.night_actions["witch_kill"]
        
        # 1. 处理狼刀和解药
        if wolf_target != -1:
            if wolf_target == witch_save:
                # 被救了，不计入死亡 (未来若有守卫，在此处处理同守同救/奶穿逻辑)
                logging.info(f"Player {wolf_target} was saved by Witch.")
            else:
                killed_this_night.add(wolf_target)
        
        # 2. 处理毒药
        if witch_kill != -1:
            killed_this_night.add(witch_kill)
            
        # 3. 执行死亡
        self.last_night_killed = list(killed_this_night)
        for pid in self.last_night_killed:
            self.kill(pid)
            
        return self.last_night_killed

    def get_snapshot(self, player_id):
        """获取当前游戏快照用于断线重连同步"""
        players_info = []
        for i in range(self.pl_count):
            players_info.append({
                "id": i,
                "alive": Tag.ALIVE in self.get_player_tags(i),
                # 不在同步中发送他人身份，保护隐私
            })
        
        return {
            "type": "sync",
            "player_id": player_id,
            "current_stage": self.current_stage.__name__ if self.current_stage else "Waiting",
            "turn": self.__turn,
            "players": players_info,
            "history": self.message_history[-10:] # 发送最近10条历史记录
        }
    
    def get_turn(self):
        return self.__turn
    
    def add_turn(self):
        self.__turn += 1
    
    def kill(self, id):
        self.__players[id].die()
    
    def revive(self, id):
        self.__players[id].revive()

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
        """检查胜负条件。返回 0 继续，1 好人胜，2 狼人胜 (采用屠边规则)"""
        wolves_alive = False
        gods_alive = False
        villagers_alive = False

        for i in range(self.pl_count):
            tags = self.get_player_tags(i)
            if Tag.ALIVE not in tags:
                continue
            
            if Tag.WEREWOLF in tags:
                wolves_alive = True
            elif Tag.GOD in tags:
                gods_alive = True
            elif Tag.VILLAGER in tags:
                villagers_alive = True
        
        # 1. 如果狼人全灭，好人获胜
        if not wolves_alive:
            logging.info("Good people won the game! All wolves eliminated.")
            return 1
            
        # 2. 如果神职全灭 或 平民全灭，狼人获胜 (屠边规则)
        if not gods_alive:
            logging.info("Werewolves won the game! All gods eliminated.")
            return 2
        if not villagers_alive:
            logging.info("Werewolves won the game! All villagers eliminated.")
            return 2
            
        return 0
    
    async def get_new_message(self, player_id : int, data : str):
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            logging.warning(f"Invalid JSON received from player {player_id}")
            return

        player_tags = self.get_player_tags(player_id)
        if Tag.ALIVE not in player_tags:
            # 检查是否有遗言权
            if player_id not in self.players_with_testament:
                logging.info(f"Dead player {player_id} attempted to send a message without testament rights")
                return

        if msg["type"] == "chat":
            # 权限检查：如果是结构化发言阶段，只有当前发言者能说话
            if self.current_speaker != -1 and player_id != self.current_speaker:
                logging.info(f"Player {player_id} attempted to speak out of turn (Current: {self.current_speaker})")
                # 可选：给玩家发送私信提示“未轮到你发言”
                return

            logging.info(f"{player_id}: {msg['msg']}")
            msg["player"] = player_id
            formatted_msg = json.dumps(msg)
            self.message_history.append(msg)
            await manager.broadcast(formatted_msg)
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
            msg_obj = {"type": "chat", "player": "System", "msg": text}
            msg = json.dumps(msg_obj)
            
            # 系统消息也存入历史（可选，为了让重连者看到最新的系统提示）
            if i == 0: # 避免重复存入
                self.message_history.append(msg_obj)
                
            logging.debug(f"Sending message to {self.__players[i].id}: {text}")
            tasks.append(manager.send_personal_message(msg, self.__players[i].id))
        if tasks:
            await asyncio.gather(*tasks)
