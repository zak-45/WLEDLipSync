import av
import base64
import io
from PIL import Image
import os
from str2bool import str2bool
import logging
import logging.config
import concurrent_log_handler
import cfg_load as cfg
import ipaddress
import re
import socket
import traceback


def check_ip_alive(ip_address, port=80, timeout=2):
    """
    efficiently check if an IP address is alive or not by testing connection on specified port
     e.g. WLED allow port 80
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
            return False  # Host is not reachable
    except Exception as error:
        logger.error(traceback.format_exc())
        logger.error(f'Error on check IP : {error}')
        return False
    finally:
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
            hostname = hostname[:-1]
        allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        return all(allowed.match(x) for x in hostname.split("."))

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
    cast_config = cfg.load('config/WLEDLipSync.ini')
    # config keys
    server_config = cast_config.get('server')
    app_config = cast_config.get('app')
    colors_config = cast_config.get('colors')
    custom_config = cast_config.get('custom')
    preset_config = cast_config.get('presets')
    desktop_config = cast_config.get('desktop')
    ws_config = cast_config.get('ws')

    return server_config, app_config, colors_config, custom_config, preset_config, desktop_config, ws_config


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


# create logger
logger = setup_logging('config/logging.ini', 'WLEDLogger.utils')
