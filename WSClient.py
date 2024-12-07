import logging
import concurrent_log_handler
import websocket
import threading
import queue
import logging
import time
import json  # Import json for serialization
import utils
import os


class WebSocketClient:
    """
    WebSocket client run in a separate thread.

    Example usage:
    client = WebSocketClient("ws://example.com/socket", retry_interval=1, max_retry_time=10)
    client.run()
    print(client.get_status())  # Outputs: "connecting", "connected", etc.
    client.send_message("Hello, WebSocket!")  # Only sends if connected
    client.stop()
    """

    def __init__(self, ws_address, retry_interval=1, max_retry_time=10, queue_check_interval=5):
        """
        Initializes a new instance of the WSClient class for managing WebSocket connections. 
        This constructor sets up the WebSocket address, retry parameters, 
        and initializes various threads and a message queue for handling communication.

        Args:
            ws_address (str): The address of the WebSocket server to connect to.
            retry_interval (int): The interval in seconds to wait before retrying a connection. Defaults to 1.
            max_retry_time (int): The maximum time in seconds to attempt reconnections. Defaults to 10.
            queue_check_interval (int): The interval in seconds to check the message queue. Defaults to 5.

        Returns:
            None

        """
        self.ws_address = ws_address
        self.retry_interval = retry_interval
        self.max_retry_time = max_retry_time
        self.queue_check_interval = queue_check_interval
        self._running = False
        self._message_queue = queue.Queue()
        self.status = "disconnected"
        self._ws = None
        self._connect_thread = None
        self._receive_thread = None
        self._send_thread = None
        self._queue_monitor_thread = None
        self._lock = threading.Lock()

    def _connect(self):
        """
        Establishes a connection to the WebSocket server and manages the connection lifecycle. 
        This method attempts to connect to the specified WebSocket address, 
        handles connection retries, and starts threads for receiving, sending, 
        and monitoring messages until the connection is closed or an error occurs.

        Returns:
            None

        """
        start_time = time.time()
        while self._running and (time.time() - start_time < self.max_retry_time):
            try:
                with self._lock:
                    self.status = "connecting"
                self._ws = websocket.create_connection(self.ws_address)
                logger.info(f"Connected to {self.ws_address}")
                with self._lock:
                    self.status = "connected"

                # Start receive, send, and queue monitor threads as daemon threads
                self._receive_thread = threading.Thread(target=self._receive)
                self._send_thread = threading.Thread(target=self._send)
                self._queue_monitor_thread = threading.Thread(target=self._queue_monitor)
                self._receive_thread.daemon = True  # Set as daemon
                self._send_thread.daemon = True  # Set as daemon
                self._queue_monitor_thread.daemon = True  # Set as daemon
                self._receive_thread.start()
                self._send_thread.start()
                self._queue_monitor_thread.start()

                # Wait for the receive thread to complete (disconnection or error)
                self._receive_thread.join()

                if not self._running:
                    break  # Stop loop if `stop()` was called
            except (websocket.WebSocketConnectionClosedException, ConnectionError) as e:
                with self._lock:
                    self.status = "retrying"
                logger.warning(f"WebSocket connection closed: {e}")
                logger.info(f"Retrying connection in {self.retry_interval} seconds...")
                time.sleep(self.retry_interval)
            except Exception as e:
                with self._lock:
                    self.status = "error"
                logger.error(f"Unexpected error: {e}")
                break

        # Final cleanup
        with self._lock:
            self.status = "disconnected" if self._running else "stopped"
        logger.info("Max retry time reached or stopped. Exiting connection loop.")

    def _receive(self):
        """
        Continuously receives messages from the WebSocket server while the client is running. 
        This method listens for incoming messages, logs them, 
        and handles any connection errors or exceptions that may occur during the receiving process.

        Returns:
            None

        """
        while self._running:
            try:
                message = self._ws.recv()
                logger.info(f"Received: {message}")
            except websocket.WebSocketConnectionClosedException:
                logger.warning("Connection closed while receiving.")
                break
            except Exception as e:
                logger.error(f"Error in receive: {e}")
                break

    def _send(self):
        """
        Continuously sends messages from the message queue to the WebSocket server while the client is running. 
        This method retrieves messages, checks the connection status, serializes messages if necessary, 
        and handles any errors that may occur during the sending process.

        Returns:
            None

        """
        while self._running:
            try:
                # Retrieve message from the queue with a timeout
                message = self._message_queue.get(timeout=1)
                with self._lock:
                    if self.status == "connected":
                        # If the message is a dictionary, serialize it to JSON string
                        if isinstance(message, dict):
                            message = json.dumps(message)
                        self._ws.send(message)
                        logger.info(f"Sent: {message}")
                    else:
                        logger.warning("Message not sent, client not connected.")
                        # self._message_queue.put(message)  # Re-enqueue the message
            except queue.Empty:
                continue  # No message to send, keep checking
            except websocket.WebSocketConnectionClosedException:
                logger.warning("Connection closed while sending.")
                # self._message_queue.put(message)  # Re-enqueue the message
                break
            except Exception as e:
                logger.error(f"Error in send: {e}")
                # self._message_queue.put(message)  # Re-enqueue the message
                break

    def _queue_monitor(self):
        """
        Monitors the message queue for the WebSocket client while the client is running. 
        This method checks the length of the message queue at regular intervals 
        and logs a warning if there are messages that are not being sent.

        Returns:
            None

        """
        while self._running:
            time.sleep(self.queue_check_interval)
            queue_length = self._message_queue.qsize()
            if queue_length > 0:
                logger.warning(f"Message queue length is {queue_length}. Messages are not being sent.")

    def run(self):
        """
        Starts the WebSocket client by initiating the connection thread. 
        This method checks if the client is already running, and if not, 
        it sets the running flag to True and starts a new thread to handle the connection process.

        Returns:
            None

        """
        if not self._running:
            self._running = True
            self._connect_thread = threading.Thread(target=self._connect)
            self._connect_thread.daemon = True  # Set as daemon
            self._connect_thread.start()
            logger.info("WebSocket client started")

    def stop(self):
        """
        Stops the WebSocket client and cleans up resources.
        This method sets the running flag to False, updates the client status,
        closes the WebSocket connection if it is open,
        clears the message queue, and waits for all associated threads to terminate.

        Returns:
            None

        """
        if not self._running:
            return
        self._running = False
        with self._lock:
            self.status = "stopped"
        # Close WebSocket connection if open
        if self._ws:
            self._ws.close()
        # Clear the message queue
        with self._message_queue.mutex:
            self._message_queue.queue.clear()
        # Wait for all threads to stop with a timeout
        if self._connect_thread:
            self._connect_thread.join(timeout=2)
        if self._receive_thread:
            self._receive_thread.join(timeout=2)
        if self._send_thread:
            self._send_thread.join(timeout=2)
        if self._queue_monitor_thread:
            self._queue_monitor_thread.join(timeout=2)
        logger.info("WebSocket client stopped")

    def send_message(self, message):
        """
        Queues a message for sending to the WebSocket server if the client is connected.
        This method checks the connection status and, if connected, adds the message to the message queue;
        otherwise, it logs a warning indicating that the message cannot be sent.

        Args:
            message: The message to be sent to the WebSocket server.

        Returns:
            None

        """
        with self._lock:
            if self.status == "connected":
                self._message_queue.put(message)
                logger.info(f"Message queued: {message}")
            else:
                logger.warning("Cannot send message: WebSocket client is not connected.")

    def get_status(self):
        """
        Retrieves the current status of the WebSocket client.
        This method returns the status while ensuring thread safety by acquiring a lock during the operation.

        Returns:
            str: The current status of the WebSocket client.

        """
        with self._lock:
            return self.status

"""
When this env var exist, this mean run from the one-file compressed executable.
Load of the config is not possible, folder config should not exist.
This avoid FileNotFoundError.
This env not exist when run from the extracted program.
Expected way to work.
"""
if "NUITKA_ONEFILE_PARENT" not in os.environ:
    # read config
    # create logger
    logger = utils.setup_logging('config/logging.ini', 'WLEDLogger.wvs')

    lip_config = utils.read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key