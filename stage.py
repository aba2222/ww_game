import asyncio
from typing import override
from player import Tag

class StageBase:
    def who_can_talk():
        return []

    def can_enter(state):
        return True
    
    async def result(state):
        return 0

class WereWolfStage:
    @override
    def who_can_talk():
        return [Tag.WEREWOLF, Tag.ALIVE]
    
    @override
    async def result(state):
        await state.send_message("Whom do you want to kill?", WereWolfStage.who_can_talk())
        try:
            await asyncio.wait_for(WereWolfStage.wait_werewolf_choice(state), timeout=180)
            print("OK")
            state.kill(state.choose)
            state.choose = None
        except TimeoutError:
            await state.send_message("You didn't kill anyone", WereWolfStage.who_can_talk())
        return 0

    async def wait_werewolf_choice(state):
        while state.choose is None:
            await asyncio.sleep(0.1)

class SeerStage:
    @override
    async def result(state):
        number = int(input("Whom do you want to predict?"))
        if Tag.GOODPERSON in state.get_player_tags(number):
            print("OK his role is good")
        else:
            print("OK his role is werewolf")

class DayStage:
    @override
    def who_can_talk():
        return [Tag.ALIVE]
    
    @override
    async def result(state):
        if state.check():
            return 1
        number = int(input("Whom do you want to vote?"))
        print("OK")
        state.kill(number)
        return 0
