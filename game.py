import logging

import stage

order = [
    stage.GuardStage,
    stage.WereWolfStage,
    stage.WitchStage,
    stage.SeerStage,
    stage.HunterStage,
    stage.DayStage,
]

async def game_main(state):
    logging.info("game started")
    index = 0
    while 1:
        if await order[index].result(state):
            break
        index += 1
        if index >= len(order):
            index = 0
    logging.info("game ended")
