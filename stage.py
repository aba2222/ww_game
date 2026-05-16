import asyncio
import logging
import json
from typing import Counter
from player import Tag, manager

class StageBase:
    def who_can_talk():
        return []

    def can_enter(state):
        return True
    
    async def result(state):
        return 0
    
    async def wait_vote(state, voter_number, candidate_list=None):
        """
        等待投票并结算结果。
        :param candidate_list: 如果指定，则只能投给列表中的人（用于 PK 环节）
        """
        while state.voted_player != voter_number:
            logging.debug(f"Waiting for votes... {state.voted_player}/{voter_number}")
            await asyncio.sleep(0.1)
            
        valid_votes = [vote for vote in state.vote if vote != -1]
        
        # 如果是 PK 环节，过滤掉不在候选名单中的投票
        if candidate_list:
            valid_votes = [vote for vote in valid_votes if vote in candidate_list]

        if not valid_votes:
            state.vote = [-1] * len(state.vote)
            state.voted_player = 0
            return -1

        vote_count = Counter(valid_votes)
        max_votes = max(vote_count.values())
        results = [player for player, count in vote_count.items() if count == max_votes]

        state.vote = [-1] * len(state.vote)
        state.voted_player = 0

        # 如果平票，返回所有最高票玩家列表
        if len(results) > 1:
            return results

        return results[0]

class WereWolfStage(StageBase):
    def who_can_talk():
        return [Tag.WEREWOLF, Tag.ALIVE]
    
    async def result(state):
        state.current_stage = WereWolfStage
        await state.send_message("Whom do you want to kill?", WereWolfStage.who_can_talk())
        try:
            voter_number = state.count_players_with_tags(WereWolfStage.who_can_talk())
            vote_result = await asyncio.wait_for(WereWolfStage.wait_vote(state, voter_number), timeout=180)
            if vote_result != -1:
                await state.send_message(f"You have killed {vote_result}", WereWolfStage.who_can_talk())
                state.kill(vote_result)
                state.last_night_killed.append(vote_result)
            else:
                await state.send_message("You didn't kill anyone (tie or no votes)", WereWolfStage.who_can_talk())
        except TimeoutError:
            await state.send_message("You didn't kill anyone (timeout)", WereWolfStage.who_can_talk())
        return 0

class WitchStage(StageBase):
    def who_can_talk():
        return [Tag.WITCH, Tag.ALIVE]

    async def result(state):
        state.current_stage = WitchStage
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in WitchStage.who_can_talk())]
        voter_number = len(voters)
        
        if voter_number == 0:
            await asyncio.sleep(10) # 即使没有女巫也增加延迟，防止信息泄露
            return 0
        
        witch_id = voters[0] # 假设场上只有一个活着的女巫
        potion_used_tonight = False
        
        # 1. 救人环节
        # 规则：解药已用则法官不再告知刀口。且女巫不能自救。
        if not state.witch_save_used:
            killed = state.last_night_killed
            if killed:
                target = killed[0]
                if target == witch_id:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "今晚你中刀了，但你不能自救。"}), witch_id)
                    await asyncio.sleep(5) # 给一点思考时间
                else:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"今晚被杀的是 {target} 号玩家。要使用灵药吗？(发送 {target} 救人，发送 -2 跳过)"}), witch_id)
                    try:
                        # 仅等待该女巫的决定
                        vote_result = await asyncio.wait_for(WitchStage.wait_vote(state, voter_number), timeout=30)
                        if vote_result == target:
                            state.revive(target)
                            state.last_night_killed.remove(target)
                            state.witch_save_used = True
                            potion_used_tonight = True
                            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你救活了 {target} 号玩家"}), witch_id)
                        else:
                            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你选择不使用灵药"}), witch_id)
                    except TimeoutError:
                        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "操作超时"}), witch_id)
            else:
                # 狼人空刀
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "今晚无人被杀。要使用灵药吗？(发送 -2 跳过)"}), witch_id)
                try:
                    await asyncio.wait_for(WitchStage.wait_vote(state, voter_number), timeout=10)
                except TimeoutError:
                    pass
        else:
            # 解药已用，不再告知刀口
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你已没有灵药，法官不再告知你今晚的伤亡情况。"}), witch_id)
            await asyncio.sleep(5)

        # 2. 毒人环节
        # 规则：同一晚只能使用一瓶药。如果今晚已经救了人，则不能毒人。
        if not potion_used_tonight:
            if not state.witch_kill_used:
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "要使用毒药吗？(发送玩家 ID 毒杀，发送 -2 跳过)"}), witch_id)
                try:
                    vote_result = await asyncio.wait_for(WitchStage.wait_vote(state, voter_number), timeout=30)
                    if vote_result >= 0 and vote_result < state.pl_count:
                        state.kill(vote_result)
                        state.last_night_killed.append(vote_result)
                        state.witch_kill_used = True
                        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你毒杀了 {vote_result} 号玩家"}), witch_id)
                    else:
                        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你选择不使用毒药"}), witch_id)
                except TimeoutError:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "操作超时"}), witch_id)
            else:
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你的毒药已经用过了"}), witch_id)
                await asyncio.sleep(5)
        else:
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "同一晚只能使用一瓶药水，你今晚已无法使用毒药。"}), witch_id)
            await asyncio.sleep(5)
            
        return 0

class SeerStage(StageBase):
    def who_can_talk():
        return [Tag.SEER, Tag.ALIVE]

    async def result(state):
        state.current_stage = SeerStage
        await state.send_message("Whom do you want to predict?", SeerStage.who_can_talk())
        try:
            voter_number = state.count_players_with_tags(SeerStage.who_can_talk())
            vote_result = await asyncio.wait_for(SeerStage.wait_vote(state, voter_number), timeout=180)
            if vote_result != -1:
                if Tag.GOODPERSON in state.get_player_tags(vote_result):
                    await state.send_message(f"Player {vote_result} is a good person", SeerStage.who_can_talk())
                else:
                    await state.send_message(f"Player {vote_result} is a werewolf", SeerStage.who_can_talk())
        except TimeoutError:
            await state.send_message("You didn't predict anyone", SeerStage.who_can_talk())
        return 0

class DayStage(StageBase):
    def who_can_talk():
        return [Tag.ALIVE]
    
    async def result(state):
        state.current_stage = DayStage
        
        # 1. 宣布夜晚结果
        if state.last_night_killed:
            deaths = ", ".join(map(str, state.last_night_killed))
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"昨晚，玩家 {deaths} 牺牲了。"}))
            state.last_night_killed = []
        else:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "昨晚是一个平安夜，没有人死亡。"}))

        # 2. 投票前胜负判定
        check_res = state.check()
        if check_res != 0:
            winner = "好人阵营" if check_res == 1 else "狼人阵营"
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"游戏结束！{winner} 获胜！"}))
            return 1

        # 3. 白天讨论与处决投票
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "白天开始。请大家讨论并投票处决一名嫌疑人。"}))
        try:
            voter_number = state.count_players_with_tags(DayStage.who_can_talk())
            vote_result = await asyncio.wait_for(DayStage.wait_vote(state, voter_number), timeout=300)
            
            # 处理平票（PK 环节）
            if isinstance(vote_result, list):
                pk_players = ", ".join(map(str, vote_result))
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"出现平票！玩家 {pk_players} 进入 PK 环节，请进行 PK 发言。"}))
                
                # PK 再次投票
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "PK 发言结束，请再次投票（只能在 PK 玩家中选择）。"}))
                vote_result = await asyncio.wait_for(DayStage.wait_vote(state, voter_number, candidate_list=vote_result), timeout=120)
                
                if isinstance(vote_result, list):
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "再次平票，今天无人被处决（平安日）。"}))
                    vote_result = -1

            if vote_result != -1:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {vote_result} 被村民投票处决了。"}))
                state.kill(vote_result)
            else:
                if not isinstance(vote_result, list): # 已经处理过 list 情况
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "无人被处决。"}))
        except TimeoutError:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "投票超时，今天无人被处决。"}))

        # 4. 处决后胜负判定
        check_res = state.check()
        if check_res != 0:
            winner = "好人阵营" if check_res == 1 else "狼人阵营"
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"游戏结束！{winner} 获胜！"}))
            return 1
            
        state.add_turn()
        return 0
