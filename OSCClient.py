import threading
import time
from pythonosc import udp_client


class OSCClient:
    """

    Simple non-blocking OSC client to send message
    Use Queue and thread to avoid block

    osc_client = OSCClient("127.0.0.1", 8000)

    osc_client.send_message("/example/address", 123)
    osc_client.send_message("/example/address", [1, 2, 3])

    osc_client.stop()

    """

    def __init__(self, ip: str, port: int):
        self.client = udp_client.SimpleUDPClient(ip, port)
        self.queue = []
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._send_messages)
        self.thread.start()

    def _send_messages(self):
        """ send the message by reading the queue """

        while self.running:
            if self.queue:
                self.lock.acquire()
                try:
                    msg = self.queue.pop(0)
                finally:
                    self.lock.release()
                self.client.send_message(msg[0], msg[1])
            # small delay (see if necessary)
            time.sleep(0.01)

    def send_message(self, address: str, value):
        """ add message to queue """
        self.lock.acquire()
        try:
            self.queue.append((address, value))
        finally:
            self.lock.release()

    def stop(self):
        self.running = False
        self.thread.join()
