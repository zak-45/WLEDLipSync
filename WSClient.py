import threading
import time
import asyncio
import websockets


class WebSocketClient:
    """
    WebSocket client

    # Create and use the WebSocket client
    ws_client = WebSocketClient("ws://127.0.0.1:8000")

    ws_client.send_message("Hello, WebSocket!")
    ws_client.send_message("Another message")

    time.sleep(2)  # Give it some time to send the messages

    ws_client.stop()

    """

    def __init__(self, uri: str):
        self.uri = uri
        self.queue = []
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._run_event_loop)
        self.thread.start()

    def _run_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._send_messages())

    async def _send_messages(self):
        async with websockets.connect(self.uri) as websocket:
            while self.running:
                if self.queue:
                    self.lock.acquire()
                    try:
                        msg = self.queue.pop(0)
                    finally:
                        self.lock.release()
                    await websocket.send(msg)
                await asyncio.sleep(0.01)

    def send_message(self, message: str):
        self.lock.acquire()
        try:
            self.queue.append(message)
        finally:
            self.lock.release()

    def stop(self):
        self.running = False
        self.thread.join()


# Example usage
if __name__ == "__main__":

    # Create and use the WebSocket client
    ws_client = WebSocketClient("ws://127.0.0.1:8000")

    ws_client.send_message("Hello, WebSocket!")
    ws_client.send_message("Another message")

    time.sleep(2)  # Give it some time to send the messages

    ws_client.stop()

