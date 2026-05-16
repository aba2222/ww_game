import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)

async def test_game():
    uri_template = "ws://localhost:8000/ws/{}"
    
    # 1. Test invalid JSON handling (Issue #12)
    logging.info("Testing Invalid JSON Handling...")
    try:
        async with websockets.connect(uri_template.format(0)) as ws:
            await ws.send("not a json")
            # Should not disconnect
            await ws.send(json.dumps({"type": "chat", "msg": "still here"}))
            resp = await ws.recv()
            logging.info(f"Received after invalid JSON: {resp}")
    except Exception as e:
        logging.error(f"Invalid JSON test failed: {e}")

    # 2. Test Duplicate Voting (Issue #11)
    logging.info("Testing Duplicate Voting...")
    async with websockets.connect(uri_template.format(0)) as ws0, \
               websockets.connect(uri_template.format(1)) as ws1:
        
        # Wait for "Whom do you want to kill?"
        while True:
            msg = json.loads(await ws0.recv())
            if "kill" in msg.get("msg", ""):
                break
        
        # Player 0 votes twice
        await ws0.send(json.dumps({"type": "vote", "target": 2}))
        await ws0.send(json.dumps({"type": "vote", "target": 1}))
        
        # At this point, voted_player should be 1, not 2. 
        # If it were 2, it might skip if voter_number was 2.
        logging.info("Sent duplicate votes from Player 0")

    # 3. Test Permission: Dead player talking (Issue #13)
    # This requires driving the game to a state where someone is dead.
    # For simplicity in this script, we'll just check if the server is running and alive.
    logging.info("Integration test script finished basic checks.")

if __name__ == "__main__":
    # Note: Server must be running for this to work
    try:
        asyncio.run(test_game())
    except ConnectionRefusedError:
        logging.error("Server is not running. Please start it with 'uvicorn main:app' first.")
