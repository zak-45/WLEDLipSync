import websocket
import threading
import queue
import logging
import time
import json  # Import json for serialization

logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logs

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
        """Main connect and retry loop."""
        start_time = time.time()
        while self._running and (time.time() - start_time < self.max_retry_time):
            try:
                with self._lock:
                    self.status = "connecting"
                self._ws = websocket.create_connection(self.ws_address)
                logging.info(f"Connected to {self.ws_address}")
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
                logging.warning(f"WebSocket connection closed: {e}")
                logging.info(f"Retrying connection in {self.retry_interval} seconds...")
                time.sleep(self.retry_interval)
            except Exception as e:
                with self._lock:
                    self.status = "error"
                logging.error(f"Unexpected error: {e}")
                break

        # Final cleanup
        with self._lock:
            self.status = "disconnected" if self._running else "stopped"
        logging.info("Max retry time reached or stopped. Exiting connection loop.")

    def _receive(self):
        """Handle incoming messages."""
        while self._running:
            try:
                message = self._ws.recv()
                logging.info(f"Received: {message}")
            except websocket.WebSocketConnectionClosedException:
                logging.warning("Connection closed while receiving.")
                break
            except Exception as e:
                logging.error(f"Error in receive: {e}")
                break

    def _send(self):
        """Handle outgoing messages from the queue."""
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
                        logging.info(f"Sent: {message}")
                    else:
                        logging.warning("Message not sent, client not connected.")
                        # self._message_queue.put(message)  # Re-enqueue the message
            except queue.Empty:
                continue  # No message to send, keep checking
            except websocket.WebSocketConnectionClosedException:
                logging.warning("Connection closed while sending.")
                # self._message_queue.put(message)  # Re-enqueue the message
                break
            except Exception as e:
                logging.error(f"Error in send: {e}")
                # self._message_queue.put(message)  # Re-enqueue the message
                break

    def _queue_monitor(self):
        """Periodically check the queue length and issue a warning if not empty."""
        while self._running:
            time.sleep(self.queue_check_interval)
            queue_length = self._message_queue.qsize()
            if queue_length > 0:
                logging.warning(f"Message queue length is {queue_length}. Messages are not being sent.")

    def run(self):
        """Start the WebSocket client."""
        if not self._running:
            self._running = True
            self._connect_thread = threading.Thread(target=self._connect)
            self._connect_thread.daemon = True  # Set as daemon
            self._connect_thread.start()
            logging.info("WebSocket client started")

    def stop(self):
        """Stop the WebSocket client immediately."""
        if self._running:
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
                self._connect_thread.join(timeout=5)
            if self._receive_thread:
                self._receive_thread.join(timeout=5)
            if self._send_thread:
                self._send_thread.join(timeout=5)
            if self._queue_monitor_thread:
                self._queue_monitor_thread.join(timeout=5)
            logging.info("WebSocket client stopped")

    def send_message(self, message):
        """Push a message into the queue only if connected."""
        with self._lock:
            if self.status == "connected":
                self._message_queue.put(message)
                logging.info(f"Message queued: {message}")
            else:
                logging.warning("Cannot send message: WebSocket client is not connected.")

    def get_status(self):
        """Return the current connection status."""
        with self._lock:
            return self.status
