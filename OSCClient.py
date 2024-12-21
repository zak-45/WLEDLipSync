import threading

from time import sleep
from pythonosc import udp_client
from configmanager import ConfigManager

cfg_mgr = ConfigManager(logger_name='WLEDLogger.osc')

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
        """
        Initializes a new instance of the OSCClient class for sending OSC messages.
        This constructor sets up the UDP client with the specified IP and port, initializes a message queue,
        and starts a separate thread for sending messages.

        Args:
            ip (str): The IP address of the OSC server to send messages to.
            port (int): The port number of the OSC server.

        Returns:
            None

        """
        self.client = udp_client.SimpleUDPClient(ip, port)
        self.queue = []
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._send_messages)
        self.thread.start()

    def _send_messages(self):
        """
        Continuously sends messages from the queue to the OSC server while the client is running.
        This method checks the message queue, acquires a lock to safely pop messages,
        and sends them to the specified address, with a small delay to manage the sending rate.

        Returns:
            None

        """
        while self.running:
            if self.queue:
                self.lock.acquire()
                try:
                    msg = self.queue.pop(0)
                finally:
                    self.lock.release()
                self.client.send_message(msg[0], msg[1])
            # small delay (see if necessary)
            sleep(0.01)

    def send_message(self, address: str, value):
        """
        Adds a message to the queue for sending to the OSC server.
        This method acquires a lock to ensure thread safety while appending the message,
        which consists of an address and a value, to the queue.

        Args:
            address (str): The OSC address to which the message will be sent.
            value: The value associated with the OSC message.

        Returns:
            None

        """
        self.lock.acquire()
        try:
            self.queue.append((address, value))
        finally:
            self.lock.release()

    def stop(self):
        """
        Stops the OSC client by setting the running flag to False and waiting for the message-sending thread to finish.
        This method ensures that all resources are properly released before the client is terminated.

        Returns:
            None

        """
        self.running = False
        self.thread.join()
