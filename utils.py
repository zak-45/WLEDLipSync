import av
import base64
import io
import os
import logging
import logging.config
import concurrent_log_handler
import cfg_load as cfg
import ipaddress
import re
import socket
import traceback

from str2bool import str2bool
from PIL import Image
from nicegui import ui

async def check_udp_port(ip_address, port=80, timeout=2):
    """
    Check if a UDP port is open on a given IP address by sending a UDP packet.
    Since UDP is connectionless, the function considers the port reachable if
    the packet is sent without an error.

    Args:
        ip_address (str): The IP address to check.
        port (int, optional): The port to check on the IP address. Default is 80.
        timeout (int, optional): The timeout duration in seconds for the operation. Default is 2 seconds.

    Returns:
        bool: True if the UDP port is reachable (i.e., the packet was sent without error), False otherwise.
    """

    sock = None
    try:
        # Create a new socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set a timeout for the socket operation
        sock.settimeout(timeout)
        # Send a dummy packet to the UDP port
        sock.sendto(b'', (ip_address, port))
        return True  # If sendto doesn't raise an exception, consider the port reachable
    except socket.timeout:
        logger.error(f"No response from {ip_address}:{port}, but packet was sent.")
        return True  # Port is likely reachable but no response was received
    except Exception as error:
        logger.error(traceback.format_exc())
        logger.error(f'Error on checking UDP port: {error}')
        return False
    finally:
        if sock:
            # Close the socket
            sock.close()


async def check_ip_alive(ip_address, port=80, timeout=2):
    """
    Efficiently check if an IP address is alive or not by testing connection on the specified port.
    e.g., WLED uses port 80.
    this use TCP connection SOCK_STREAM, so not for UDP

    Args:
        ip_address (str): The IP address to check.
        port (int, optional): The port to check on the IP address. Default is 80.
        timeout (int, optional): The timeout duration in seconds for the connection attempt. Default is 2 seconds.

    Returns:
        bool: True if the IP address is reachable on the specified port, False otherwise.
    """

    sock = None
    try:
        # Create a new socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set a timeout for the connection attempt
        sock.settimeout(timeout)
        # Attempt to connect to the IP address and port
        result = sock.connect_ex((ip_address, port))
        # Check if the connection was successful
        if result == 0:
            return True  # Host is reachable
        else:
            logger.error(f"Failed to connect to {ip_address}:{port}. Error code: {result}")
            return False  # Host is not reachable
    except Exception as error:
        logger.error(traceback.format_exc())
        logger.error(f'Error on check IP: {error}')
        return False
    finally:
        if sock:
            # Close the socket
            sock.close()

def validate_ip_address(ip_string):
    """
    Check if the given string is a valid IP address format or a reachable hostname.

    Args:
        ip_string (str): The IP address or hostname to validate.

    Returns:
        bool: True if the input is a valid IP address or a reachable hostname, False otherwise.
    """

    def is_valid_hostname(hostname):
        """Check if the string is a valid hostname."""
        if len(hostname) > 255:
            return False
        if hostname[-1] == ".":
            hostname = hostname[:-1]  # Strip the trailing dot if present
        allowed = re.compile(r"^(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        return all(allowed.match(part) for part in hostname.split("."))

    # Check if it's a valid IP address
    try:
        ipaddress.ip_address(ip_string)
        return True
    except ValueError:
        pass

    # Check if it's a valid hostname
    if is_valid_hostname(ip_string):
        try:
            # Check if hostname is reachable
            socket.gethostbyname(ip_string)
            return True
        except socket.gaierror:
            return False

    return False

def read_config():
    # load config file
    lip_config = cfg.load('config/WLEDLipSync.ini')
    # config keys
    server_config = lip_config.get('server')
    app_config = lip_config.get('app')
    colors_config = lip_config.get('colors')
    custom_config = lip_config.get('custom')

    return server_config, app_config, colors_config, custom_config


def setup_logging(config_path='logging_config.ini', handler_name: str = None):
    if os.path.exists(config_path):
        logging.config.fileConfig(config_path, disable_existing_loggers=True)
        # trick: use the same name for all modules, ui.log will receive message from alls
        config_data = read_config()
        if str2bool(config_data[1]['log_to_main']):
            v_logger = logging.getLogger('WLEDLogger')
        else:
            v_logger = logging.getLogger(handler_name)
        v_logger.debug(f"Logging configured using {config_path} for {handler_name}")
    else:
        logging.basicConfig(level=logging.INFO)
        v_logger = logging.getLogger(handler_name)
        v_logger.warning(f"Logging config file {config_path} not found. Using basic configuration.")

    return v_logger


def convert_audio(input_file, output_file):
    """
    Convert audio file from one format to another (e.g., MP3 to WAV or WAV to MP3).

    # Example usage
    # convert_audio('media/audio/input.mp3', 'output.wav')
    # convert_audio('media/audio/input.wav', 'output.mp3')

    :param input_file: Path to the input audio file
    :param output_file: Path to the output audio file
    :return: None
    """
    try:
        # Open the input audio file
        input_container = av.open(input_file)

        # Determine the format of the output file based on its extension
        output_format = output_file.split('.')[-1]

        # Create an output audio file
        output_container = av.open(output_file, mode='w', format=output_format)

        # Add a stream for the output file
        if output_format == 'wav':
            output_stream = output_container.add_stream('pcm_s16le', rate=44100)  # WAV: PCM format, 16-bit samples
        elif output_format == 'mp3':
            output_stream = output_container.add_stream('mp3', rate=44100)  # MP3: MPEG format
        else:
            raise ValueError("Unsupported output format. Supported formats are 'wav' and 'mp3'.")

        for frame in input_container.decode(audio=0):
            # Encode the audio frame
            for packet in output_stream.encode(frame):
                output_container.mux(packet)

        # Finalize the output file by flushing the stream
        for packet in output_stream.encode():  # Encode any remaining data
            output_container.mux(packet)

        # Close the output container
        output_container.close()

        # Close the input container
        input_container.close()

        logger.info(f"Conversion complete: {input_file} to {output_file}")

    except Exception as e:
        logger.error(f"An error occurred during conversion: {e}")


def image_array_to_base64(nparray):
    """
    this will convert a np image into base64
    :param nparray:
    :return: base64 string
    """
    # Convert NumPy array to PIL Image
    image = Image.fromarray(nparray)
    # Save the image to a bytes buffer
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    # Encode the bytes as Base64
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    # The img_str is the Base64 string representation of the image
    return img_str


def apply_custom():
    """
    Layout Colors come from config file
    bg image can be customized
    :return:
    """
    ui.colors(primary=color_config['primary'],
              secondary=color_config['secondary'],
              accent=color_config['accent'],
              dark=color_config['dark'],
              positive=color_config['positive'],
              negative=color_config['negative'],
              info=color_config['info'],
              warning=color_config['warning']
              )

    ui.query('body').style(f'background-image: url({custom_config["bg-image"]}); '
                           'background-size: cover;'
                           'background-repeat: no-repeat;'
                           'background-position: center;')



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
    logger = setup_logging('config/logging.ini', 'WLEDLogger.utils')

    lip_config = read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key


