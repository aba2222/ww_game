import asyncio
import logging
from typing import Counter, override
from player import Tag

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
        vote_count = Counter(valid_votes)
        max_votes = max(vote_count.values())
        result = [player for player, count in vote_count.items() if count == max_votes]

        state.vote = [-1] * len(state.vote)
        state.voted_player = 0

        if len(result) > 1:
            return -1

        return result[0]

class WereWolfStage(StageBase):
    @override
    def who_can_talk():
        return [Tag.WEREWOLF, Tag.ALIVE]
    
    @override
    async def result(state):
        await state.send_message("Whom do you want to kill?", WereWolfStage.who_can_talk())
        try:
            voter_number = state.count_players_with_tags(WereWolfStage.who_can_talk())
            vote_result = await asyncio.wait_for(WereWolfStage.wait_vote(state, voter_number), timeout=180)
            await state.send_message(f"You have killed {vote_result}", WereWolfStage.who_can_talk())
            if vote_result != -1:
                state.kill(vote_result)
        except TimeoutError:
            await state.send_message("You didn't kill anyone", WereWolfStage.who_can_talk())
        return 0

class SeerStage(StageBase):
    @override
    def who_can_talk():
        return [Tag.SEER, Tag.ALIVE]

    @override
    async def result(state):
        await state.send_message("Whom do you want to predict?", SeerStage.who_can_talk())
        try:
            voter_number = state.count_players_with_tags(SeerStage.who_can_talk())
            vote_result = await asyncio.wait_for(SeerStage.wait_vote(state, voter_number), timeout=180)
            if vote_result != -1:
                if Tag.GOODPERSON in state.get_player_tags(vote_result):
                    await state.send_message("OK his role is good", SeerStage.who_can_talk())
                else:
                    await state.send_message("OK his role is werewolf", SeerStage.who_can_talk())
        except TimeoutError:
            await state.send_message("You didn't predict anyone", SeerStage.who_can_talk())

class DayStage(StageBase):
    @override
    def who_can_talk():
        return [Tag.ALIVE]
    
    @override
    async def result(state):
        if state.check():
            return 1
        #number = int(input("Whom do you want to vote?"))
        await state.send_message("OK", DayStage.who_can_talk())
        #state.kill(number)
        return 0
