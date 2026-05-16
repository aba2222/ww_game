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
    
    async def wait_vote(state, voter_number):
        while state.voted_player != voter_number:
            logging.debug(f"Waiting for votes... {state.voted_player}/{voter_number}")
            await asyncio.sleep(0.1)
            
        valid_votes = [vote for vote in state.vote if vote != -1]
        if not valid_votes:
            state.vote = [-1] * len(state.vote)
            state.voted_player = 0
            return -1

        vote_count = Counter(valid_votes)
        max_votes = max(vote_count.values())
        result = [player for player, count in vote_count.items() if count == max_votes]

        state.vote = [-1] * len(state.vote)
        state.voted_player = 0

        if len(result) > 1:
            return -1

        return result[0]

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
        
        # 1. Announce night results
        if state.last_night_killed:
            deaths = ", ".join(map(str, state.last_night_killed))
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"Last night, players {deaths} were killed."}))
            state.last_night_killed = []
        else:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "It was a peaceful night, no one died."}))

        # 2. Check for game over before voting
        check_res = state.check()
        if check_res != 0:
            winner = "Good People" if check_res == 1 else "Werewolves"
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"Game Over! {winner} won!"}))
            return 1

        # 3. Discussion and Voting for execution
        await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "It's daytime. Discuss and vote who to execute."}))
        try:
            voter_number = state.count_players_with_tags(DayStage.who_can_talk())
            vote_result = await asyncio.wait_for(DayStage.wait_vote(state, voter_number), timeout=300)
            
            if vote_result != -1:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"Player {vote_result} has been executed by the village."}))
                state.kill(vote_result)
            else:
                await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "No one was executed (tie or no votes)."}))
        except TimeoutError:
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": "Voting timed out. No one was executed."}))

        # 4. Final check after execution
        check_res = state.check()
        if check_res != 0:
            winner = "Good People" if check_res == 1 else "Werewolves"
            await manager.broadcast(json.dumps({"type": "chat", "player": "System", "msg": f"Game Over! {winner} won!"}))
            return 1
            
        state.add_turn()
        return 0
