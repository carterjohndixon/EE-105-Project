import asyncio
import json
import sys
import traceback

sys.path.insert(0, "..")          # the ee105 folder sits next to this project folder

import websockets

from game import cpu_move, judge, explain, read_player

KIND = "cnn"                      # "cnn" (smallCNN) or "mobilenet", as trained
WEIGHTS = "rps_cnn.pt"            # file saved with model.save(...)
HOST, PORT = "localhost", 8765
COUNTDOWN = (3, 2, 1)
STEP = 0.7                        # seconds per countdown number

clients = set()
busy = False


async def send(msg):
    websockets.broadcast(clients, json.dumps(msg))


async def play(cam, model):
    """One round: the computer picks first, countdown, then the camera reads the player."""
    global busy
    if busy:
        return
    busy = True
    try:
        cpu = cpu_move()                                   # chosen BEFORE the player shows a hand
        for n in COUNTDOWN:
            await send({"state": "countdown", "n": n})
            await asyncio.sleep(STEP)
        await send({"state": "go"})
        player = await asyncio.to_thread(read_player, model, cam.snap)
        if player is None:
            await send({"state": "none"})
            return
        await send({"state": "result", "player": player, "cpu": cpu,
                    "result": judge(player, cpu), "rule": explain(player, cpu)})
    except Exception as e:                                 # keep the server alive, tell the page
        traceback.print_exc()
        await send({"state": "error", "message": str(e)})
    finally:
        busy = False


async def main():
    import ee105
    from model import load

    sim = "--sim" in sys.argv
    cam = ee105.connect_camera(simulate=True if sim else None)
    model = load(KIND, WEIGHTS)

    async def handler(ws):
        clients.add(ws)
        await ws.send(json.dumps({"state": "ready"}))
        try:
            async for m in ws:
                if str(m).strip() == "start":
                    await play(cam, model)
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, HOST, PORT):
        print(f"Ready: ws://{HOST}:{PORT}   (open rps.html in the browser, Ctrl+C to stop)")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
