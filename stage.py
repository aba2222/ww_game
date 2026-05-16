import asyncio
import logging
import json
from typing import Counter
from player import Tag, manager

class DetonateInterrupt(Exception):
    """用于处理狼人自爆的中断异常"""
    pass

class StageBase:
    def who_can_talk():
        return []

    def can_enter(state):
        return True
    
    async def result(state):
        return 0
    
    async def wait_vote(state, voter_number, candidate_list=None, weighted=False):
        """
        等待投票并结算结果。
        :param candidate_list: 如果指定，则只能投给列表中的人
        :param weighted: 是否计算权重（警长 1.5 票）
        """
        while state.voted_player != voter_number:
            # 实时检查是否有狼人自爆
            if state.detonated_wolf != -1:
                raise DetonateInterrupt()
                
            logging.debug(f"Waiting for votes... {state.voted_player}/{voter_number}")
            await asyncio.sleep(0.1)
            
        # 统计选票
        vote_tally = Counter()
        for i in range(state.pl_count):
            target = state.vote[i]
            if target != -1 and target != -2: # -2 是弃权
                if candidate_list and target not in candidate_list:
                    continue
                weight = state.get_vote_weight(i) if weighted else 1.0
                vote_tally[target] += weight

        state.vote = [-1] * len(state.vote)
        state.voted_player = 0

        if not vote_tally:
            return -1

        max_votes = max(vote_tally.values())
        results = [player for player, count in vote_tally.items() if count == max_votes]

        if len(results) > 1:
            return results

        return results[0]

async def handle_hunter_shoot(state, hunter_id):
    """处理猎人开枪逻辑"""
    if Tag.HUNTER in state.get_player_tags(hunter_id) and state.hunter_shootable:
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {hunter_id} 是猎人，由于死亡，可以翻牌发动技能！"}))
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"请猎人玩家 {hunter_id} 选择要开枪带走的目标号码（输入 -2 放弃）："}))
        
        try:
            state.current_stage = HunterStage 
            # 猎人开枪不受自爆影响
            vote_result = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=60)
            
            if isinstance(vote_result, int) and vote_result >= 0 and vote_result < state.pl_count:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"【砰！】猎人开枪带走了玩家 {vote_result}。"}))
                state.kill(vote_result)
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "猎人选择了不开枪。"}))
        except TimeoutError:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "操作超时，猎人没能开出这枪。"}))

async def handle_wolfking_shoot(state, wolfking_id):
    """处理狼王开枪逻辑"""
    if Tag.WOLFKING in state.get_player_tags(wolfking_id):
        # 狼王被毒不能开枪 (根据werewolf-guide，不同规则不同，这里采用主流规则：毒杀不能开枪)
        if state.night_actions["witch_kill"] == wolfking_id:
             await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {wolfking_id} 是狼王，但由于被毒杀，无法发动开枪技能。"}))
             return

        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {wolfking_id} 是狼王，由于死亡，可以翻牌发动技能！"}))
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"请狼王玩家 {wolfking_id} 选择要开枪带走的目标号码（输入 -2 放弃）："}))
        
        try:
            state.current_stage = WolfKingStage 
            vote_result = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=60)
            
            if isinstance(vote_result, int) and vote_result >= 0 and vote_result < state.pl_count:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"【砰！】狼王开枪带走了玩家 {vote_result}。"}))
                state.kill(vote_result)
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "狼王选择了不开枪。"}))
        except TimeoutError:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "操作超时，狼王没能开出这枪。"}))

class SheriffElectionStage(StageBase):
    """警长竞选阶段 (仅第一天)"""
    async def result(state):
        if state.get_turn() != 1:
            return 0
            
        state.current_stage = SheriffElectionStage
        state.candidates = []
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "【警长竞选】想要上警竞选警长的玩家，请在 15 秒内发送 -99 确认。"}))
        
        # 1. 动态报名阶段
        await asyncio.sleep(15)
        candidates = state.candidates
        
        if not candidates:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "无人上警，本局无警长。"}))
            return 0

        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"参选玩家为：{candidates}。进入警上发言环节。"}))
        
        # 2. 警上发言与动态退水
        try:
            for pid in list(candidates): # 使用 list 副本以防遍历时修改
                if pid not in state.candidates: continue # 已退水
                
                state.current_speaker = pid
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"现在由竞选玩家 {pid} 发言。退水请发送 -2。"}))
                
                # 等待发言时间，同时监听自爆
                for _ in range(300): # 30s
                    if state.detonated_wolf != -1: raise DetonateInterrupt()
                    if pid not in state.candidates: break # 动态退水
                    await asyncio.sleep(0.1)
            
            state.current_speaker = -1
            
            # 3. 确定最终候选人
            candidates = state.candidates
            if len(candidates) == 1:
                winner = candidates[0]
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"仅剩玩家 {winner} 参选，自动当选警长！"}))
                state.set_sheriff(winner)
                return 0
            elif not candidates:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "候选人全部退水，本局无警长。"}))
                return 0

            # 4. 警下投票
            voters = [i for i in range(state.pl_count) if i not in candidates and Tag.ALIVE in state.get_player_tags(i)]
            if not voters:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "所有存活玩家均已上警，无法投票，本局无警长。"}))
                return 0
                
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "发言结束，请警下玩家投票。"}))
            state.active_voters = voters
            vote_result = await asyncio.wait_for(StageBase.wait_vote(state, len(voters), candidate_list=candidates), timeout=60)
            state.active_voters = []
            
            if isinstance(vote_result, int) and vote_result != -1:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"竞选结束，玩家 {vote_result} 当选警长！"}))
                state.set_sheriff(vote_result)
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "由于平票或无人投票，本局无警长。"}))
        except DetonateInterrupt:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "【自爆】由于狼人自爆，警徽消失，本局无警长。"}))
            return 0
            
        return 0

class GuardStage(StageBase):
    def who_can_talk():
        return [Tag.GUARD, Tag.ALIVE]

    async def result(state):
        state.current_stage = GuardStage
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in GuardStage.who_can_talk())]
        voter_number = len(voters)
        
        if voter_number == 0:
            await asyncio.sleep(5)
            return 0
            
        guard_id = voters[0]
        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"请选择今晚要守护的目标号码（上轮守护：{state.last_guard_target}，输入 -2 空守）："}), guard_id)
        
        try:
            vote_result = await asyncio.wait_for(GuardStage.wait_vote(state, voter_number), timeout=30)
            
            if isinstance(vote_result, int) and vote_result >= 0:
                if vote_result == state.last_guard_target:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "不能连续两晚守护同一人，本次操作无效。"}), guard_id)
                else:
                    state.night_actions["guard_protect"] = vote_result
                    state.last_guard_target = vote_result
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你今晚守护了 {vote_result} 号玩家"}), guard_id)
            else:
                state.last_guard_target = -1
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你今晚选择了空守"}), guard_id)
        except TimeoutError:
            state.last_guard_target = -1
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "操作超时，你今晚选择了空守"}), guard_id)
            
        return 0

class WereWolfStage(StageBase):
    def who_can_talk():
        return [Tag.WEREWOLF, Tag.WOLFKING, Tag.ALIVE]
    
    async def result(state):
        state.current_stage = WereWolfStage
        state.reset_night_actions() 
        await state.send_message("请选择今晚要袭击的目标号码：", WereWolfStage.who_can_talk())
        try:
            voter_number = state.count_players_with_tags(WereWolfStage.who_can_talk())
            vote_result = await asyncio.wait_for(WereWolfStage.wait_vote(state, voter_number), timeout=180)
            
            if isinstance(vote_result, list): 
                import random
                vote_result = random.choice(vote_result)

            if vote_result != -1:
                await state.send_message(f"狼人选择了袭击 {vote_result} 号玩家", WereWolfStage.who_can_talk())
                state.night_actions["wolf_kill"] = vote_result
            else:
                await state.send_message("狼人今晚空刀了", WereWolfStage.who_can_talk())
        except TimeoutError:
            await state.send_message("袭击超时，狼人今晚空刀了", WereWolfStage.who_can_talk())
        return 0

class WitchStage(StageBase):
    def who_can_talk():
        return [Tag.WITCH, Tag.ALIVE]

    async def result(state):
        state.current_stage = WitchStage
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in WitchStage.who_can_talk())]
        voter_number = len(voters)
        
        if voter_number == 0:
            await asyncio.sleep(10)
            return 0
        
        witch_id = voters[0]
        potion_used_tonight = False
        
        if not state.witch_save_used:
            target = state.night_actions["wolf_kill"]
            if target != -1:
                if target == witch_id:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "今晚你中刀了，但你不能自救。"}), witch_id)
                    await asyncio.sleep(5)
                else:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"今晚被杀的是 {target} 号玩家。要使用灵药吗？(发送 {target} 救人，发送 -2 跳过)"}), witch_id)
                    try:
                        vote_result = await asyncio.wait_for(WitchStage.wait_vote(state, voter_number), timeout=30)
                        if vote_result == target:
                            state.night_actions["witch_save"] = target
                            state.witch_save_used = True
                            potion_used_tonight = True
                            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你救活了 {target} 号玩家"}), witch_id)
                        else:
                            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你选择不使用灵药"}), witch_id)
                    except TimeoutError:
                        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "操作超时"}), witch_id)
            else:
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "今晚无人被杀。要使用灵药吗？(发送 -2 跳过)"}), witch_id)
                try:
                    await asyncio.wait_for(WitchStage.wait_vote(state, voter_number), timeout=10)
                except TimeoutError: pass
        else:
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你已没有灵药，法官不再告知你今晚的伤亡情况。"}), witch_id)
            await asyncio.sleep(5)

        if not potion_used_tonight:
            if not state.witch_kill_used:
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "要使用毒药吗？(发送玩家 ID 毒杀，发送 -2 跳过)"}), witch_id)
                try:
                    vote_result = await asyncio.wait_for(WitchStage.wait_vote(state, voter_number), timeout=30)
                    if isinstance(vote_result, int) and vote_result >= 0 and vote_result < state.pl_count:
                        state.night_actions["witch_kill"] = vote_result
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
        await state.send_message("请选择今晚要查验的目标号码：", SeerStage.who_can_talk())
        try:
            voter_number = state.count_players_with_tags(SeerStage.who_can_talk())
            vote_result = await asyncio.wait_for(SeerStage.wait_vote(state, voter_number), timeout=180)
            if isinstance(vote_result, int) and vote_result != -1:
                if Tag.WEREWOLF in state.get_player_tags(vote_result) or Tag.WOLFKING in state.get_player_tags(vote_result):
                    await state.send_message(f"{vote_result} 号玩家的身份是：狼人", SeerStage.who_can_talk())
                else:
                    await state.send_message(f"{vote_result} 号玩家的身份是：好人", SeerStage.who_can_talk())
        except TimeoutError:
            await state.send_message("查验超时，你今晚没有获得任何信息", SeerStage.who_can_talk())
        return 0

class HunterStage(StageBase):
    def who_can_talk():
        return [Tag.HUNTER, Tag.ALIVE]

    async def result(state):
        state.current_stage = HunterStage
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in HunterStage.who_can_talk())]
        if not voters:
            await asyncio.sleep(2)
            return 0
        
        hunter_id = voters[0]
        if state.hunter_shootable:
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你的开枪状态：【正常】"}), hunter_id)
        else:
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "你的开枪状态：【中毒】"}), hunter_id)
        
        await asyncio.sleep(3)
        return 0

class WolfKingStage(StageBase):
    def who_can_talk():
        return [Tag.WOLFKING, Tag.ALIVE]

    async def result(state):
        state.current_stage = WolfKingStage
        # 仅仅是为了夜晚告知
        await asyncio.sleep(2)
        state.settle_night()
        return 0

class DayStage(StageBase):
    def who_can_talk():
        return [Tag.ALIVE]
    
    async def result(state):
        state.current_stage = DayStage
        
        try:
            # 1. 结算并宣布夜晚结果
            killed_ids = state.last_night_killed
            if killed_ids:
                deaths = ", ".join(map(str, killed_ids))
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"昨晚，玩家 {deaths} 牺牲了。"}))
                
                for pid in killed_ids:
                    # 处理猎人开枪
                    if Tag.HUNTER in state.get_player_tags(pid) and pid != state.night_actions["witch_kill"]:
                        await handle_hunter_shoot(state, pid)
                    # 处理狼王开枪
                    if Tag.WOLFKING in state.get_player_tags(pid):
                        await handle_wolfking_shoot(state, pid)
                
                # 警长牺牲处理
                for pid in killed_ids:
                    if pid == state.sheriff_id:
                        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "【重要】警长牺牲了！请移交或撕掉警徽。"}))
                        try:
                            transfer_res = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=30)
                            if isinstance(transfer_res, int) and transfer_res >= 0:
                                state.set_sheriff(transfer_res)
                            else: state.set_sheriff(-1)
                        except TimeoutError: state.set_sheriff(-1)

                # 遗言权判定
                testament_ids = [pid for pid in killed_ids if pid != state.night_actions["witch_kill"] and state.get_turn() == 1]
                if testament_ids:
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "请死亡玩家发表遗言。"}))
                    for pid in testament_ids:
                        state.current_speaker = pid
                        await asyncio.sleep(30)
                    state.current_speaker = -1

                state.last_night_killed = []
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "昨晚是一个平安夜。"}))

            # 2. 讨论前判定
            if state.check() != 0: return 1

            # 3. 白天讨论环节
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "进入白天讨论环节。"}))
            alive_players = [i for i in range(state.pl_count) if Tag.ALIVE in state.get_player_tags(i)]
            # 排序：从警长左手位开始
            if state.sheriff_id != -1 and state.sheriff_id in alive_players:
                idx = alive_players.index(state.sheriff_id)
                alive_players = alive_players[idx+1:] + alive_players[:idx+1]

            for pid in alive_players:
                if state.detonated_wolf != -1: raise DetonateInterrupt()
                state.current_speaker = pid
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"现在由玩家 {pid} 发言。"}))
                await asyncio.sleep(60)
            state.current_speaker = -1

            # 4. 处决投票
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "讨论结束，开始处决投票。"}))
            voter_number = state.count_players_with_tags(DayStage.who_can_talk())
            state.active_voters = [i for i in range(state.pl_count) if Tag.ALIVE in state.get_player_tags(i)]
            vote_result = await asyncio.wait_for(DayStage.wait_vote(state, voter_number, weighted=True), timeout=180)
            state.active_voters = []
            
            # 处理平票与 PK (省略部分重复逻辑以保重点)
            if isinstance(vote_result, int) and vote_result != -1:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {vote_result} 被处决。"}))
                state.kill(vote_result)
                if Tag.HUNTER in state.get_player_tags(vote_result): await handle_hunter_shoot(state, vote_result)
                if Tag.WOLFKING in state.get_player_tags(vote_result): await handle_wolfking_shoot(state, vote_result)
            
        except DetonateInterrupt:
            # 入夜前确保结算自爆狼
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "阶段中断，立即入夜。"}))
            
        state.add_turn()
        return 0
