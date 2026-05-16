import asyncio
import logging
import json
import random
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
        """
        while state.voted_player != voter_number:
            if state.detonated_wolf != -1:
                raise DetonateInterrupt()
            await asyncio.sleep(0.1)
            
        vote_tally = Counter()
        for i in range(state.pl_count):
            target = state.vote[i]
            if target != -1 and target != -2:
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
        await manager.broadcast(json.dumps({"type": "sound", "effect": "gunshot"}))
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {hunter_id} 是猎人，由于死亡，可以翻牌发动技能！"}))
        await state.start_stage("HunterShoot", 60) 
        
        try:
            state.current_stage = HunterStage 
            vote_result = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=60)
            
            if isinstance(vote_result, int) and vote_result >= 0 and vote_result < state.pl_count:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"【砰！】猎人开枪带走了玩家 {vote_result}。"}))
                state.kill(vote_result)
                await manager.broadcast(json.dumps({"type": "sound", "effect": "death"}))
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "猎人选择了不开枪。"}))
        except TimeoutError:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "操作超时，猎人没能开出这枪。"}))

async def handle_wolfking_shoot(state, wolfking_id):
    """处理狼王开枪逻辑"""
    if Tag.WOLFKING in state.get_player_tags(wolfking_id):
        if state.night_actions["witch_kill"] == wolfking_id:
             await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {wolfking_id} 是狼王，但由于被毒杀，无法发动开枪技能。"}))
             return

        await manager.broadcast(json.dumps({"type": "sound", "effect": "gunshot"}))
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {wolfking_id} 是狼王，由于死亡，可以翻牌发动技能！"}))
        await state.start_stage("WolfKingShoot", 60)
        
        try:
            state.current_stage = WolfKingStage 
            vote_result = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=60)
            
            if isinstance(vote_result, int) and vote_result >= 0 and vote_result < state.pl_count:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"【砰！】狼王开枪带走了玩家 {vote_result}。"}))
                state.kill(vote_result)
                await manager.broadcast(json.dumps({"type": "sound", "effect": "death"}))
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "狼王选择了不开枪。"}))
        except TimeoutError:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "操作超时，狼王没能开出这枪。"}))

class SheriffElectionStage(StageBase):
    async def result(state):
        if state.get_turn() != 1:
            return 0
        state.current_stage = SheriffElectionStage
        await state.start_stage("SheriffElectionStage", 15)
        state.candidates = []
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "【警长竞选】想要上警竞选警长的玩家，请在 15 秒内点击“上警”确认。"}))
        
        await asyncio.sleep(15)
        candidates = state.candidates
        if not candidates:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "无人上警，本局无警长。"}))
            return 0

        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"参选玩家为：{candidates}。进入警上发言环节。"}))
        try:
            for pid in list(candidates):
                if pid not in state.candidates: continue
                state.current_speaker = pid
                duration = 45
                await state.start_stage("SheriffSpeech", duration)
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"现在由竞选玩家 {pid} 发言。退水请点击“弃权”。"}))
                for _ in range(duration * 10):
                    if state.detonated_wolf != -1: raise DetonateInterrupt()
                    if pid not in state.candidates: break
                    await asyncio.sleep(0.1)
            
            state.current_speaker = -1
            candidates = state.candidates
            if len(candidates) == 1:
                winner = candidates[0]
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"仅剩玩家 {winner} 参选，自动当选警长！"}))
                state.set_sheriff(winner)
                return 0
            elif not candidates:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "候选人全部退水，本局无警长。"}))
                return 0

            voters = [i for i in range(state.pl_count) if i not in candidates and Tag.ALIVE in state.get_player_tags(i)]
            if not voters:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "所有存活玩家均已上警，无法投票，本局无警长。"}))
                return 0
                
            await state.start_stage("SheriffVote", 60)
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
        await manager.broadcast(json.dumps({"type": "sound", "effect": "night_fall"}))
        duration = 30
        await state.start_stage("GuardStage", duration, GuardStage.who_can_talk())
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in GuardStage.who_can_talk())]
        if not voters:
            await asyncio.sleep(5); return 0
            
        guard_id = voters[0]
        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"请选择要守护的目标（上轮：{state.last_guard_target}）："}), guard_id)
        try:
            vote_result = await asyncio.wait_for(GuardStage.wait_vote(state, 1), timeout=duration)
            if isinstance(vote_result, int) and vote_result >= 0:
                if vote_result == state.last_guard_target:
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "不能连守，操作无效。"}), guard_id)
                else:
                    state.night_actions["guard_protect"] = vote_result
                    state.last_guard_target = vote_result
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你守护了 {vote_result} 号玩家"}), guard_id)
            else:
                state.last_guard_target = -1
        except TimeoutError:
            state.last_guard_target = -1
        return 0

class WereWolfStage(StageBase):
    def who_can_talk():
        return [Tag.WEREWOLF, Tag.WOLFKING, Tag.ALIVE]
    
    async def result(state):
        state.current_stage = WereWolfStage
        duration = 60
        await state.start_stage("WereWolfStage", duration, WereWolfStage.who_can_talk())
        state.reset_night_actions() 
        try:
            voter_number = state.count_players_with_tags(WereWolfStage.who_can_talk())
            vote_result = await asyncio.wait_for(WereWolfStage.wait_vote(state, voter_number), timeout=duration)
            if isinstance(vote_result, list):
                vote_result = random.choice(vote_result)
            if vote_result != -1:
                state.night_actions["wolf_kill"] = vote_result
        except TimeoutError: pass
        return 0

class WitchStage(StageBase):
    def who_can_talk():
        return [Tag.WITCH, Tag.ALIVE]

    async def result(state):
        state.current_stage = WitchStage
        duration = 60
        await state.start_stage("WitchStage", duration, WitchStage.who_can_talk())
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in WitchStage.who_can_talk())]
        if not voters:
            await asyncio.sleep(5); return 0
        
        witch_id = voters[0]
        potion_used_tonight = False
        if not state.witch_save_used:
            target = state.night_actions["wolf_kill"]
            if target != -1 and target != witch_id:
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"今晚 {target} 号中刀。要救吗？"}), witch_id)
                try:
                    vote_result = await asyncio.wait_for(WitchStage.wait_vote(state, 1), timeout=30)
                    if vote_result == target:
                        state.night_actions["witch_save"] = target
                        state.witch_save_used = True
                        potion_used_tonight = True
                        await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你救活了 {target}"}), witch_id)
                except TimeoutError: pass
        
        if not potion_used_tonight and not state.witch_kill_used:
            await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": "要用毒药吗？"}), witch_id)
            try:
                vote_result = await asyncio.wait_for(WitchStage.wait_vote(state, 1), timeout=30)
                if isinstance(vote_result, int) and vote_result >= 0:
                    state.night_actions["witch_kill"] = vote_result
                    state.witch_kill_used = True
                    await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"你毒杀了 {vote_result}"}), witch_id)
            except TimeoutError: pass
        return 0

class SeerStage(StageBase):
    def who_can_talk():
        return [Tag.SEER, Tag.ALIVE]

    async def result(state):
        state.current_stage = SeerStage
        duration = 30
        await state.start_stage("SeerStage", duration, SeerStage.who_can_talk())
        voters = [i for i in range(state.pl_count) if all(tag in state.get_player_tags(i) for tag in SeerStage.who_can_talk())]
        if not voters:
            await asyncio.sleep(5); return 0
        try:
            vote_result = await asyncio.wait_for(SeerStage.wait_vote(state, 1), timeout=duration)
            if isinstance(vote_result, int) and vote_result != -1:
                is_wolf = Tag.WEREWOLF in state.get_player_tags(vote_result) or Tag.WOLFKING in state.get_player_tags(vote_result)
                await manager.send_personal_message(json.dumps({"type": "chat", "player": "System", "msg": f"{vote_result} 号是：{'狼人' if is_wolf else '好人'}"}), voters[0])
        except TimeoutError: pass
        return 0

class HunterStage(StageBase):
    def who_can_talk():
        return [Tag.HUNTER, Tag.ALIVE]
    async def result(state):
        state.current_stage = HunterStage
        await state.start_stage("HunterStage", 5, HunterStage.who_can_talk())
        await asyncio.sleep(5)
        return 0

class WolfKingStage(StageBase):
    def who_can_talk():
        return [Tag.WOLFKING, Tag.ALIVE]
    async def result(state):
        state.current_stage = WolfKingStage
        await state.start_stage("WolfKingStage", 5, WolfKingStage.who_can_talk())
        await asyncio.sleep(5)
        state.settle_night()
        return 0

class DayStage(StageBase):
    def who_can_talk():
        return [Tag.ALIVE]
    
    async def result(state):
        state.current_stage = DayStage
        await manager.broadcast(json.dumps({"type": "sound", "effect": "day_break"}))
        try:
            killed_ids = state.last_night_killed
            if killed_ids:
                deaths = ", ".join(map(str, killed_ids))
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"昨晚，玩家 {deaths} 牺牲了。"}))
                await manager.broadcast(json.dumps({"type": "sound", "effect": "death"}))
                for pid in killed_ids:
                    if Tag.HUNTER in state.get_player_tags(pid) and pid != state.night_actions["witch_kill"]:
                        await handle_hunter_shoot(state, pid)
                    if Tag.WOLFKING in state.get_player_tags(pid) and pid != state.night_actions["witch_kill"]:
                        await handle_wolfking_shoot(state, pid)
                
                for pid in killed_ids:
                    if pid == state.sheriff_id:
                        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "【重要】警长牺牲了！请移交或撕掉警徽。"}))
                        await state.start_stage("SheriffTransfer", 30)
                        try:
                            transfer_res = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=30)
                            if isinstance(transfer_res, int) and transfer_res >= 0:
                                state.set_sheriff(transfer_res)
                            else: state.set_sheriff(-1)
                        except TimeoutError: state.set_sheriff(-1)

                testament_ids = [pid for pid in killed_ids if pid != state.night_actions["witch_kill"] and state.get_turn() == 1]
                if testament_ids:
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "请死亡玩家发表遗言。"}))
                    for pid in testament_ids:
                        await state.start_stage("Testament", 30)
                        state.current_speaker = pid
                        await asyncio.sleep(30)
                    state.current_speaker = -1
                state.last_night_killed = []
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "昨晚是一个平安夜。"}))

            if state.check() != 0: return 1

            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "进入白天讨论环节。"}))
            alive_players = [i for i in range(state.pl_count) if Tag.ALIVE in state.get_player_tags(i)]
            if state.sheriff_id != -1 and state.sheriff_id in alive_players:
                idx = alive_players.index(state.sheriff_id)
                alive_players = alive_players[idx+1:] + alive_players[:idx+1]

            for pid in alive_players:
                if state.detonated_wolf != -1: raise DetonateInterrupt()
                state.current_speaker = pid
                duration = 60
                await state.start_stage("Discussion", duration)
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"现在由玩家 {pid} 发言。"}))
                await asyncio.sleep(duration)
            state.current_speaker = -1

            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "讨论结束，开始处决投票。"}))
            duration = 60
            await state.start_stage("EliminationVote", duration)
            voter_number = state.count_players_with_tags(DayStage.who_can_talk())
            state.active_voters = [i for i in range(state.pl_count) if Tag.ALIVE in state.get_player_tags(i)]
            vote_result = await asyncio.wait_for(DayStage.wait_vote(state, voter_number, weighted=True), timeout=duration)
            state.active_voters = []
            
            if isinstance(vote_result, int) and vote_result != -1:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"玩家 {vote_result} 被处决。"}))
                await manager.broadcast(json.dumps({"type": "sound", "effect": "death"}))
                state.kill(vote_result)
                if Tag.HUNTER in state.get_player_tags(vote_result): await handle_hunter_shoot(state, vote_result)
                if Tag.WOLFKING in state.get_player_tags(vote_result): await handle_wolfking_shoot(state, vote_result)
                
                if vote_result == state.sheriff_id:
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "【重要】警长被处决！请移交或撕掉警徽。"}))
                    await state.start_stage("SheriffTransfer", 30)
                    try:
                        transfer_res = await asyncio.wait_for(StageBase.wait_vote(state, 1), timeout=30)
                        if isinstance(transfer_res, int) and transfer_res >= 0:
                            state.set_sheriff(transfer_res)
                        else: state.set_sheriff(-1)
                    except: state.set_sheriff(-1)

                if state.get_turn() == 1:
                    await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "请被处决玩家发表遗言。"}))
                    await state.start_stage("Testament", 30)
                    state.current_speaker = vote_result
                    await asyncio.sleep(30)
                    state.current_speaker = -1
            
        except DetonateInterrupt:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "阶段中断，立即入夜。"}))
            await manager.broadcast(json.dumps({"type": "sound", "effect": "detonate"}))
            
        state.add_turn()
        return 0
