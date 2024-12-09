"""
a: zak-45
d: 03/12/2024
v: 1.0.0.0

Utilities for WLEDLipSync

"""
import asyncio
import av
import base64
import io
import os
import logging
import logging.config
import concurrent_log_handler
import cfg_load as cfg
import contextlib
import ipaddress
import re
import socket
import traceback
import cv2
import time
import json
import subprocess
import sys

import requests
import zipfile

from str2bool import str2bool
from PIL import Image
from nicegui import ui, run
from pathlib import Path


def check_spleeter_is_running(obj, file_path, check_interval: float = 1.0):
    """
    Continuously checks for the existence of a specific file in a specified folder.
    Use to know if Chataigne - Spleeter has finished as it run in a separate process.

    Args:
        obj: nicegui element : spleeter button
        file_path (str): The full path of the file to check for.
        check_interval (float): The time in seconds to wait between checks. Defaults to 1.0.

    Returns:
        None
    """
    # extract file name only
    file_name = os.path.basename(file_path)
    file_info = os.path.splitext(file_name)
    file = file_info[0]
    file_folder = app_config['audio_folder'] + file + '/'
    file_to_check = f"{file_folder}vocals.mp3"
    #
    while not os.path.isfile(file_to_check):
        logger.debug(f"Waiting for {file_to_check} to be created...")
        time.sleep(check_interval)
    logger.debug(f"File {file_to_check} exists!")
    obj.props(remove='loading')


def download_github_directory_as_zip(repo_url: str, destination: str, directory_path: str = '*'):
    """
    Downloads a specific directory from a GitHub repository as a ZIP file.
    # Example usage
    download_github_directory_as_zip('https://github.com/user/repo', 'path/to/directory/', 'local_directory')

    Args:
        repo_url (str): The URL of the GitHub repository (e.g., 'https://github.com/user/repo').
        destination (str): The local directory where the ZIP file will be extracted.
        directory_path (str): The path of the directory within the repository to download.
            if = * full extract

    Returns:
        None
    """
    # Construct the ZIP file URL for the specific directory
    zip_url = f"{repo_url}/archive/refs/heads/main.zip"  # Adjust branch name if necessary

    try:
        # Download the ZIP file
        response = requests.get(zip_url)
        response.raise_for_status()  # Raise an error for bad responses

        # Extract the ZIP file
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            if directory_path != '*':
                # Extract only the specific directory
                for file_info in zip_file.infolist():
                    if file_info.filename.startswith(directory_path):
                        zip_file.extract(file_info, destination)
            else:
                zip_file.extractall(destination)
            logger.info(f'Download {repo_url}, extract "{directory_path}" to {destination}')
    except requests.RequestException as e:
        logger.info(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        logger.info('Error: The downloaded file is not a valid ZIP file.')


def extract_zip_with_7z(zip_file, destination):
    """Extract a ZIP file using 7z.exe to a specified folder.

    This function runs the 7z.exe command-line tool to extract the contents
    of the provided ZIP file to the specified destination folder. It ensures
    that the extraction process is executed in a subprocess.

    Args:
        zip_file (str): The path to the ZIP file to be extracted.
        destination (str): The folder where the contents of the ZIP file will be extracted.

    Raises:
        subprocess.CalledProcessError: If the extraction process fails.
    """

    z_path = f"{chataigne_modules_folder()}/SpleeterGUI-Chataigne-Module-main/xtra/win/7-ZipPortable/App/7-Zip64/7z.exe"
    try:
        subprocess.run([z_path, 'x', zip_file, f'-o{destination}', '-y'], check=True)
    except Exception as e:
        logger.error(f'Error with 7zip {e}')


def extract_from_url(source, destination, msg, seven_zip: bool = False):
    """
    Download and extract a ZIP file from a given URL.

    This function retrieves a ZIP file from the specified source URL and
    extracts its contents to the provided destination directory. It also logs
    a message upon successful extraction.
    With longPathName this could provide errors, better to use 7zip instead if available.
    (7zip is provided with SpleeterGUI Chataigne module)

    Args:
        source (str): The URL of the ZIP file to download.
        destination (str): The directory where the contents of the ZIP file will be extracted.
        msg (str): The message to log after successful extraction.
        seven_zip: default to False, if True, will use 7zip to extract (Win only).

    Raises:
        requests.HTTPError: If the HTTP request to download the ZIP file fails.
    """
    # Download the ZIP file
    response = requests.get(source)
    response.raise_for_status()  # Raise an error for bad responses
    # Extract the ZIP file
    if not seven_zip:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            zip_file.extractall(destination)
    else:
        # specific to win32 for the long path name  problem
        file_path = 'tmp/Pysp310.zip'
        with open(file_path, 'wb') as file:
            file.write(response.content)
        extract_zip_with_7z(file_path, destination)

    logger.info(msg)


def download_spleeter():
    """
    Downloads necessary data for the Spleeter application from specified GitHub repositories.

    This function first downloads the SpleeterGUI-Chataigne-Module directory as a ZIP file and extracts it to the
    specified local path. It then attempts to download and extract a specific version of the PySpleeter application,
    handling any errors that may occur during the download or extraction process.

    Returns:
        None

    Raises:
        requests.RequestException: If there is an error during the download of the repository.
        zipfile.BadZipFile: If the downloaded file is not a valid ZIP file.
    """
    # module
    logger.info('downloading data for Spleeter ...')
    download_github_directory_as_zip('https://github.com/zak-45/SpleeterGUI-Chataigne-Module', chataigne_modules_folder())
    logger.info('Chataigne Module Spleeter downloaded')
    # wait a few sec
    time.sleep(3)
    #  extract python portable spleeter
    seven_zip = sys.platform.lower() == 'win32'
    try:
        extract_from_url(
            f'https://github.com/zak-45/SpleeterGUI-Chataigne-Module/releases/download/0.0.0.0/{python_portable_zip()}',
            f'{chataigne_folder()}/xtra',
            'PySpleeter downloaded',
            seven_zip,
        )
    except requests.RequestException as e:
        logger.info(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        logger.info('Error: The downloaded file is not a valid ZIP file.')


def download_chataigne():
    """
    Downloads the Chataigne application from a specified GitHub release.

    This function attempts to download a ZIP file containing the Chataigne application and extracts it to the
    specified local directory. It handles potential errors that may occur during the download or extraction process.

    Returns:
        None

    Raises:
        requests.RequestException: If there is an error during the download of the repository.
        zipfile.BadZipFile: If the downloaded file is not a valid ZIP file.
    """
    logger.info('Downloading Portable Chataigne...')
    try:
        extract_from_url(
            'https://github.com/zak-45/WLEDLipSync/releases/download/0.0.0.0/Chataigne-1.9.24-win.zip',
            './chataigne/win',
            'chataigne downloaded',
        )
    except requests.RequestException as e:
        logger.info(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        logger.info('Error: The downloaded file is not a valid ZIP file.')


def download_rhubarb():
    logger.info('Downloading Portable Rhubarb...')
    try:
        extract_from_url(
            f'{rhubarb_url()}',
            f'{rhubarb_folder()}',
            'rhubarb downloaded',
        )
    except requests.RequestException as e:
        logger.info(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        logger.info('Error: The downloaded file is not a valid ZIP file.')


def chataigne_settings(port=None):
    audio_folder = str(Path(app_config['audio_folder']).resolve())
    app_folder = os.getcwd()

    if os.path.isfile(f'{app_folder}/chataigne/WLEDLipSync.noisette'):
        with open(f'{app_folder}/chataigne/WLEDLipSync.noisette', 'r', encoding='utf-8') as settings:
            data = json.load(settings)

        if port is not None:
            access_or_set_dict_value(data_dict=data,
                                     input_string='modules.items[3].params.parameters[5].value',
                                     new_value=int(port))
        else:

            access_or_set_dict_value(data_dict=data,
                                     input_string='modules.items[0].params.containers.spleeterParams.parameters[0].value',
                                     new_value=f'{app_folder}/chataigne/modules/SpleeterGUI-Chataigne-Module-main/spleeter.cmd')

            access_or_set_dict_value(data_dict=data,
                                     input_string='modules.items[0].params.containers.spleeterParams.parameters[2].value',
                                     new_value=f'{audio_folder}')

            access_or_set_dict_value(data_dict=data,
                                     input_string='modules.items[3].scripts.items[0].parameters[0].value',
                                     new_value=f'{app_folder}/chataigne/LipSync.js')

        with open(f'{app_folder}/chataigne/WLEDLipSync.noisette', 'w', encoding='utf-8') as new_settings:
            json.dump(data, new_settings, ensure_ascii=False, indent=4)

        logger.info('Put chataigne settings')


def chataigne_exe_file():
    """
    Determine the executable file path based on the operating system.

    This function checks the current platform and returns the appropriate
    path to the Chataigne executable for Windows, Linux, or macOS. If the
    platform is not recognized, it returns 'unknown'.

    Returns:
        str: The path to the Chataigne executable or 'unknown' if the platform is not supported.
    """

    if sys.platform.lower() == 'win32':
        return 'chataigne/win/Chataigne.exe'
    elif sys.platform.lower() == 'linux':
        return 'chataigne/linux/chataigne'
    elif sys.platform.lower() == 'macos':
        return 'chataigne/mac/chataigne'
    else:
        return 'unknown'


def chataigne_folder():
    if sys.platform.lower() == 'win32':
        return 'chataigne/win/Documents/Chataigne'
    elif sys.platform.lower() == 'linux':
        return 'chataigne/linux/Chataigne'
    elif sys.platform.lower() == 'macos':
        return 'chataigne/mac/Chataigne'
    else:
        return 'unknown'

def rhubarb_folder():
    if sys.platform.lower() == 'win32':
        return 'rhubarb/win'
    elif sys.platform.lower() == 'linux':
        return 'rhubarb/linux'
    elif sys.platform.lower() == 'macos':
        return 'rhubarb/mac'
    else:
        return 'unknown'


def rhubarb_url():
    if sys.platform.lower() == 'win32':
        return 'https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.13.0/Rhubarb-Lip-Sync-1.13.0-Windows.zip'
    elif sys.platform.lower() == 'linux':
        return 'https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.13.0/Rhubarb-Lip-Sync-1.13.0-Linux.zip'
    elif sys.platform.lower() == 'macos':
        return 'https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.13.0/Rhubarb-Lip-Sync-1.13.0-macOS.zip'
    else:
        return 'unknown'


def python_portable_zip():
    if sys.platform.lower() == 'win32':
        return 'spleeter-portable-windows-x86_64.zip'
    elif sys.platform.lower() == 'linux':
        return 'spleeter-portable-linux-x86_64.zip'
    elif sys.platform.lower() == 'macos':
        return 'spleeter-portable-darwin-universal2.zip'
    else:
        return 'unknown'


def chataigne_modules_folder():
    """
    Determine the Spleeter module folder path based on the operating system.

    This function checks the current platform and returns the appropriate
    path to the Spleeter module folder for Windows, Linux, or macOS. If the
    platform is not recognized, it returns 'unknown'.

    Returns:
        str: The path to the Spleeter module folder or 'unknown' if the platform is not supported.
    """
    if sys.platform.lower() == 'win32':
        return 'chataigne/win/Documents/Chataigne/modules'
    elif sys.platform.lower() == 'linux':
        return 'chataigne/linux/Chataigne/modules'
    elif sys.platform.lower() == 'macos':
        return 'chataigne/mac/Chataigne/modules'
    else:
        return 'unknown'


async def run_install_chataigne(obj, dialog):
    """
    Manages the asynchronous installation process for the Chataigne application.

    This function orchestrates the download and installation of Chataigne and its dependencies, including Spleeter.
    It updates the user interface to notify the user of the installation progress and finalizes the installation process.

    Args:
        obj: An object that contains the sender for UI updates.
        dialog: The dialog to be closed once the installation process starts.

    Returns:
        None

    Raises:
        None
    """
    logger.debug('run chataigne installation')
    dialog.close()
    #
    ui.notify('Download Portable Chataigne', position='center', type='info')
    await run.io_bound(download_chataigne)
    #
    # we will wait a few sec before continue
    time.sleep(2)
    #
    ui.notify('Download data for spleeter... this will take some time', position='center', type='info')
    await run.io_bound(download_spleeter)
    #
    # we will wait a few sec before continue
    time.sleep(2)
    #
    ui.notify('Finalize Chataigne installation', position='center', type='info')
    await run.io_bound(chataigne_settings)
    #
    # set UI after installation
    obj.sender.props(remove='loading')
    obj.sender.set_text('RELOAD APP')
    obj.sender.on('click', lambda: ui.navigate.to('/'))
    ui.notify('Reload your APP to use Chataigne/Spleeter', position='center', type='warning')


async def run_install_rhubarb():
    logger.debug('run rhubarb installation')
    #
    ui.notify('Download data for rhubarb', position='center', type='info')
    await run.io_bound(download_rhubarb)
    #


async def ask_install_chataigne(obj):
    def stop():
        obj.sender.props(remove='loading')
        dialog.close()

    logger.info('install chataigne')
    obj.sender.props(add='loading')
    with ui.dialog() as dialog, ui.card():
        dialog.open()
        ui.label('This will install portable Chataigne - Spleeter')
        ui.label('Need some space ....')
        ui.label('Are You Sure ?')
        with ui.row():
            ui.button('Yes', on_click=lambda: run_install_chataigne(obj, dialog))
            ui.button('No', on_click=stop)


def find_tmp_folder():
    """
    retrieve tmp folder in the same way as Spleeter.js
    used for mp3 tags
    
    """
    path_tmp = os.getenv('TMP')
    path_tmpdir = os.getenv('TMPDIR')
    path_temp = os.getenv('TEMP')

    if path_tmp is not None:
        return path_tmp
    elif path_tmpdir is not None:
        return path_tmpdir
    elif path_temp is not None:
        return path_temp
    else:
        return None


def access_or_set_dict_value(data_dict, input_string, new_value=None):
    """
    Accesses or sets a value in a nested dictionary using a dot-separated string with array indices.

    This function allows for dynamic access to dictionary values based on a specified path, which can include
    both dictionary keys and array indices. If a new value is provided, it sets the value at the specified path;
    otherwise, it retrieves the current value.

    example usage:
    input_string = "projectSettings.containers.dashboardSettings.parameters[0].controlAddress"

    # Access
    value = access_or_set_dict_value(data_dict, input_string)
    logger.info(value)  # Output: 'old_value'

    # Set a new value
    new_value = "new_value"
    access_or_set_dict_value(data_dict, input_string, new_value)
    logger.info(data_dict['projectSettings']['containers']['dashboardSettings']['parameters'][0]['controlAddress'])
                # Output: 'new_value'

    Args:
        data_dict (dict): The dictionary to access or modify.
        input_string (str): The dot-separated string representing the path to the desired value.
        new_value: The new value to set at the specified path (default is None).

    Returns:
        The value at the specified path if new_value is None; otherwise, returns None after setting the value.
    """

    # Split the input string by dots and array indices
    parts = re.split(r'(\.|\[\d+\])', input_string)

    # Remove empty strings from the list
    parts = [part for part in parts if part not in ['.', '']]

    # Initialize the current level of the dictionary
    current_level = data_dict

    # Iterate through the parts, but stop before the last part
    for part in parts[:-1]:
        if part.startswith('[') and part.endswith(']'):
            # If part is an index (e.g., [0]), convert to integer
            index = int(part[1:-1])
            current_level = current_level[index]
        else:
            # Otherwise, it's a dictionary key
            current_level = current_level[part]

    # Access or set the value at the last part
    last_part = parts[-1]
    if last_part.startswith('[') and last_part.endswith(']'):
        index = int(last_part[1:-1])
        if new_value is None:
            return current_level[index]
        else:
            current_level[index] = new_value
    else:
        if new_value is None:
            return current_level[last_part]
        else:
            current_level[last_part] = new_value


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
        if result == 0:
            return True  # Host is reachable
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
    with contextlib.suppress(ValueError):
        ipaddress.ip_address(ip_string)
        return True
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
    """
    Reads the configuration settings from a specified INI file.
    This function loads the configuration file, retrieves various configuration sections,
    and returns them for use in the application.

    Returns:
        tuple: A tuple containing the server configuration,
        application configuration, colors configuration, and custom configuration.

    """
    # load config file
    lip_cfg = cfg.load('config/WLEDLipSync.ini')
    # config keys
    server_cfg = lip_cfg.get('server')
    app_cfg = lip_cfg.get('app')
    colors_cfg = lip_cfg.get('colors')
    custom_cfg = lip_cfg.get('custom')

    return server_cfg, app_cfg, colors_cfg, custom_cfg


def setup_logging(config_path='logging_config.ini', handler_name: str = None):
    """
    Sets up logging configuration based on a specified configuration file. 
    This function checks for the existence of a logging configuration file, applies the configuration if found, 
    and returns a logger instance configured according to the settings, 
    or falls back to a basic configuration if the file is not found.

    Args:
        config_path (str): The path to the logging configuration file. Defaults to 'logging_config.ini'.
        handler_name (str, optional): The name of the logger handler to use. Defaults to None.

    Returns:
        logging.Logger: The configured logger instance.

    """
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
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


async def load_image_async(img_path: str):
    """
    Loads an image asynchronously from the specified file path.

    This function reads an image file and converts its color format from BGR to RGB.
    It is designed to be used in an asynchronous context to avoid blocking the main thread.

    Args:
        img_path (str): The file path of the image to be loaded.

    Returns:
        cv2: The loaded image in RGB format, or None if the image could not be loaded.
    """

    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(None, cv2.imread, img_path, cv2.IMREAD_COLOR)
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def find_cue_point(time_cue, cue_points):
    """ find mouth card near provided time """

    if not cue_points or 'mouthCues' not in cue_points:
        return [{"start": "None", "end": "None", "value": "None"}, {"start": "None", "end": "None", "value": "None"}]

    threshold = 5
    actual_cue = {"start": "None", "end": "None", "value": "None"}
    nearest_cue = {"start": "None", "end": "None", "value": "None"}
    smallest_diff = float('inf')

    for cue in cue_points['mouthCues']:
        # find actual cue
        if cue['start'] <= time_cue < cue['end']:
            actual_cue = {"start": cue['start'], "end": cue['end'], "value": cue['value']}
        # find nearest cue
        diff = abs(time_cue - cue['start'])
        if diff < smallest_diff and diff < threshold:
            smallest_diff = diff
            nearest_cue = {"start": cue['start'], "end": cue['end'], "value": cue['value']}

    return actual_cue, nearest_cue


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
