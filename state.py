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
            "guard_protect": -1,
        }
        self.last_guard_target = -1 # 守卫不能连续两晚守同一人
        self.hunter_shootable = True # 猎人是否能开枪（被毒不能开枪）
        self.players_with_testament = [] # 记录有遗言权的死者ID
        self.current_speaker = -1 # 当前发言者ID，-1表示自由发言或非发言阶段
        self.sheriff_id = -1 # 警长ID，-1表示无警长
        self.detonated_wolf = -1 # 记录当前自爆的狼人ID，-1表示无自爆
        self.candidates = [] # 警长竞选候选人名单
        self.active_voters = [] # 当前环节需要投票的人员名单

    def set_sheriff(self, player_id):
        """设置警长"""
        self.sheriff_id = player_id

    def get_vote_weight(self, player_id):
        """获取玩家投票权重：警长为 1.5，其他为 1.0"""
        return 1.5 if player_id == self.sheriff_id else 1.0

    def reset_night_actions(self):
        """重置夜晚行动记录"""
        self.night_actions = {
            "wolf_kill": -1,
            "witch_save": -1,
            "witch_kill": -1,
            "guard_protect": -1,
        }
        self.detonated_wolf = -1 # 入夜后重置自爆状态

    def settle_night(self):
        """结算夜晚的所有行动，计算最终死亡名单"""
        killed_this_night = set()
        
        wolf_target = self.night_actions["wolf_kill"]
        witch_save = self.night_actions["witch_save"]
        witch_kill = self.night_actions["witch_kill"]
        guard_protect = self.night_actions["guard_protect"]
        
        # 1. 处理狼刀、解药和守护
        if wolf_target != -1:
            # 同守同救 (奶穿) 逻辑：守卫守了且女巫救了，人还是会死
            if wolf_target == guard_protect and wolf_target == witch_save:
                logging.info(f"Player {wolf_target} was milked-through (Guard + Witch) and died.")
                killed_this_night.add(wolf_target)
            # 正常守护成功
            elif wolf_target == guard_protect:
                logging.info(f"Player {wolf_target} was protected by Guard.")
            # 正常解药救成功
            elif wolf_target == witch_save:
                logging.info(f"Player {wolf_target} was saved by Witch.")
            # 无人保护
            else:
                killed_this_night.add(wolf_target)
        
        # 2. 处理毒药 (毒药无视守护)
        if witch_kill != -1:
            killed_this_night.add(witch_kill)
            # 被毒杀的猎人不能开枪
            if Tag.HUNTER in self.get_player_tags(witch_kill):
                self.hunter_shootable = False
                logging.info(f"Hunter {witch_kill} was poisoned and lost shooting ability.")
            
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
                "sheriff": i == self.sheriff_id,
                "tags": [tag.name for tag in self.get_player_tags(i)] if i == player_id else [] # 只发自己的身份标签
            })
        
        return {
            "type": "sync",
            "player_id": player_id,
            "current_stage": self.current_stage.__name__ if self.current_stage else "Waiting",
            "turn": self.__turn,
            "players": players_info,
            "history": self.message_history[-10:],
            "detonated_wolf": self.detonated_wolf,
            "current_speaker": self.current_speaker
        }
    
    async def start_stage(self, stage_name, duration, tags=None):
        """通知前端一个新阶段开始，包含倒计时信息"""
        msg = {
            "type": "stage_start",
            "stage": stage_name,
            "duration": duration,
            "allowed_tags": [tag.name for tag in tags] if tags else []
        }
        await manager.broadcast(json.dumps(msg))
    
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
            
            if Tag.WEREWOLF in tags or Tag.WOLFKING in tags:
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
            # 检查是否有权限执行当前操作
            stage_name = self.current_stage.__name__ if self.current_stage else ""
            is_shooting_stage = stage_name in ["HunterStage", "WolfKingStage"]
            if player_id not in self.players_with_testament and not is_shooting_stage:
                logging.info(f"Dead player {player_id} attempted to send a message without permission")
                return

        if msg["type"] == "chat":
            if self.current_speaker != -1 and player_id != self.current_speaker:
                logging.info(f"Player {player_id} attempted to speak out of turn")
                return

            logging.info(f"{player_id}: {msg['msg']}")
            msg["player"] = player_id
            formatted_msg = json.dumps(msg)
            self.message_history.append(msg)
            await manager.broadcast(formatted_msg)

        elif msg["type"] == "vote":
            if self.current_stage is None:
                return
            
            target = msg.get("target", -1)
            stage_name = self.current_stage.__name__

            # 特殊指令：上警报名 (-99)
            if target == -99 and stage_name == "SheriffElectionStage":
                if player_id not in self.candidates:
                    self.candidates.append(player_id)
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {player_id} 已报名竞选警长。"}))
                return

            # 特殊指令：退水 (-2)
            if target == -2 and stage_name == "SheriffElectionStage":
                if player_id == self.current_speaker and player_id in self.candidates:
                    self.candidates.remove(player_id)
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {player_id} 宣布退水，退出竞选。"}))
                return

            # 普通投票逻辑（包含弃权 -2）
            if self.vote[player_id] != -1:
                logging.info(f"{player_id} attempted to vote again")
                return
            
            # 权限检查
            allowed_tags = self.current_stage.who_can_talk()
            if not all(tag in player_tags for tag in allowed_tags) and player_id not in self.active_voters:
                 # 特殊处理：如果是处决投票，检查是否在 active_voters 中
                 logging.info(f"Player {player_id} attempted to vote without proper tags/permission")
                 return

            logging.info(f"{player_id} voted {target}")
            self.vote[player_id] = target
            self.voted_player += 1

        elif msg["type"] == "detonate":
            # 狼人自爆逻辑 (仅限活着且属于狼人阵营的玩家)
            if (Tag.WEREWOLF in player_tags or Tag.WOLFKING in player_tags) and Tag.ALIVE in player_tags:
                if self.current_stage.__name__ in ["DayStage", "SheriffElectionStage"]:
                    self.detonated_wolf = player_id
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"【！！！】玩家 {player_id} 翻牌自爆！当前阶段立即终止。"}))
                    self.kill(player_id)

    async def send_message(self, text, tags):
        tasks = []
        for i in range(self.pl_count):
            player_tags = self.get_player_tags(i)
            if not all(tag in player_tags for tag in tags):
                continue
            msg_obj = {"type": "chat", "player": "System", "msg": text}
            msg = json.dumps(msg_obj)
            if i == 0:
                self.message_history.append(msg_obj)
            tasks.append(manager.send_personal_message(msg, self.__players[i].id))
        if tasks:
            await asyncio.gather(*tasks)
