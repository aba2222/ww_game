from state import GameState
import stage

order = [
    stage.WereWolfStage,
    stage.SeerStage,
    stage.DayStage,
]

async def game_main(state):
    index = 0
    while 1:
        if await order[index].result(state):
            break
        index += 1
        if index >= order.count():
            index = 0
    print("game ended")
