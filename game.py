import logging

import stage

order = [
    stage.WereWolfStage,
<<<<<<< Updated upstream
    stage.SeerStage,
=======
#    stage.WitchStage,
    stage.SeerStage,
#    stage.HunterStage,
    stage.SheriffElectionStage,
>>>>>>> Stashed changes
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
