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
import chataigne

import requests
import zipfile
import io



from str2bool import str2bool
from PIL import Image
from nicegui import ui, run
from pathlib import Path

cha = chataigne.ChataigneWrapper()


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
            print(f'Directory "{directory_path}" from repo {repo_url} downloaded and extracted to {destination}')
    except requests.RequestException as e:
        print(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        print('Error: The downloaded file is not a valid ZIP file.')


def extract_from_lip_sync(source, destination, msg):
        # Download the ZIP file
    response = requests.get(source)
    response.raise_for_status()  # Raise an error for bad responses
        # Extract the ZIP file
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        zip_file.extractall(destination)
        print(msg)


def download_spleeter():
    print('downloading data for Spleeter ...')
    download_github_directory_as_zip('https://github.com/zak-45/SpleeterGUI-Chataigne-Module','./chataigne/modules')
    print('Module Spleeter downloaded')
    try:
        extract_from_lip_sync(
            'https://github.com/zak-45/WLEDLipSync/releases/download/0.0.0.0/PySpleeter-win.zip',
            './chataigne/win/Documents/Chataigne/xtra',
            'PySpleeter downloaded',
        )
    except requests.RequestException as e:
        print(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        print('Error: The downloaded file is not a valid ZIP file.')


def download_chataigne():
    print('downloading data for Chataigne...')
    download_github_directory_as_zip('https://github.com/zak-45/SpleeterGUI-Chataigne-Module','./chataigne/modules')
    print('Spleeter downloaded')
    try:
        extract_from_lip_sync(
            'https://github.com/zak-45/WLEDLipSync/releases/download/0.0.0.0/Chataigne-1.9.24-win.zip',
            './chataigne/win',
            'chataigne downloaded',
        )
    except requests.RequestException as e:
        print(f'Error downloading repository: {e}')
    except zipfile.BadZipFile:
        print('Error: The downloaded file is not a valid ZIP file.')

def finalize_chataigne():
    print('finalize')


async def run_install_chataigne(obj, dialog):
    print('install it...')
    dialog.close()
    ui.notify('download data for chataigne')
    await run.io_bound(download_chataigne)
    ui.notify('download data for spleeter')
    await run.io_bound(download_spleeter)
    ui.notify('finalize')
    await run.io_bound(finalize_chataigne)
    obj.sender.props(remove='loading')

async def install_chataigne(obj):
    def stop():
        obj.sender.props(remove='loading')
        dialog.close()

    print('install chataigne')
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


def run_chataigne(action):
    """
    Run or Stop chataigne

    """
    if action == 'run':
        noisette = str(Path('./chataigne/WLEDLipSync.noisette').resolve())
        cha.run(headless=False, file_name=noisette)
        print('start chataigne')

    elif action == 'stop':
        cha.stop_process()
        print('stop chataigne')


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
    print(value)  # Output: 'old_value'

    # Set a new value
    new_value = "new_value"
    access_or_set_dict_value(data_dict, input_string, new_value)
    print(data_dict['projectSettings']['containers']['dashboardSettings']['parameters'][0]['controlAddress'])
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


async def get_audio_duration(player: str = ''):
    """
    Get audio duration
    :param player: ID of the player object (str)
    :return: duration
    """

    return await ui.run_javascript(f'document.getElementById("{player}").duration;', timeout=2)


async def wavesurfer():
    """
    Sets up the CSS and JavaScript for the wavesurfer component.

    This function adds the necessary CSS styles for the waveform display and
    includes the JavaScript module required for the wavesurfer functionality.
    It ensures that the waveform is styled correctly and is interactive for user actions.

    Returns:
        None
    """

    ui.add_css('''
    #waveform {
    margin: 0 28px; /* waveform */
    height: 192; /* Set a height for the waveform */
    cursor: crosshair; /* Change cursor to indicate clickable area */
    }
    .blink {
        animation: blinker 1s linear infinite;
        color: yellow;
    }

    @keyframes blinker {
        50% { opacity: 0; }
    }
    ''')

    ui.add_body_html('''    
    <script type="module">
        import "/assets/js/wledlipsync.js"
    </script>    
    ''')


async def drag_drop():
    ui.add_body_html('''    
    <script src="/assets/js/dragdrop.js"></script>    
    ''')


async def get_player_time():
    """
    get player current playing time
    """

    return round(
        await ui.run_javascript(
            "document.getElementById('player_vocals').currentTime;", timeout=3
        ),
        2,
    )


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


async def run_gencuedata():
    """
    execute javascript function to generate
    data when click on waveform for focus on the mouth card
    """
    await ui.run_javascript('genCueData();', timeout=5)


def create_marker(position, value):
    """ run java to add marker on the waveform """

    ui.run_javascript(f'add_marker({position},"{value}");', timeout=5)


def clear_markers():
    """ run java to clear all markers """

    ui.run_javascript('clear_markers();', timeout=5)


async def mouth_time_buffer_edit():
    """
    Displays a dialog for editing the mouth time buffer in the application. 
    This asynchronous function creates a full-screen dialog containing an iframe for the editor and 
    provides buttons to open the editor in a new tab or to close the dialog.

    Returns:
        None

    """
    buffer_dialog = ui.dialog() \
        .props(add='full-width full-height transition-show="slide-up" transition-hide="slide-down"')

    with buffer_dialog:
        buffer_dialog.open()
        editor_card = ui.card().classes('w-full')
        with editor_card:
            ui.html(
                '''                
            <iframe src="/edit" frameborder="0" 
            style="overflow:hidden;overflow-x:hidden;overflow-y:hidden;
                    height:100%;width:100%;
                    position:absolute;top:0px;left:0px;right:0px;bottom:0px" 
            height="100%" width="100%">
            </iframe>
            '''
            )
            with ui.page_sticky(position='top-right', x_offset=85, y_offset=28):
                with ui.row():
                    new_editor = ui.button(icon='edit', color='yellow')
                    new_editor.on('click', lambda: ui.navigate.to('/edit', new_tab=True))
                    new_editor.props(add='round outline size="8px"')
                    new_editor.tooltip('Open editor in new tab')
                    close = ui.button(icon='close', color='red')
                    close.on('click', lambda: buffer_dialog.close())
                    close.props(add='round outline size="8px"')
                    close.tooltip('Close editor')


class AnimatedElement:
    """
    Add animation to UI Element, in / out
        In for create element
        Out for delete element
    Following is necessary as it's based on Animate.css
    # Add Animate.css to the HTML head
    ui.add_head_html(""
    <link rel="stylesheet" href="./assets/css/animate.min.css"/>
    "")
    app.add_static_files('/assets', 'assets')
    Param:
        element_type : nicegui element e.g. card, label, ...
        animation_name : see https://animate.style/
        duration : custom animation delay
    """

    def __init__(self, element_type: type[any], animation_name_in='fadeIn', animation_name_out='fadeOut', duration=1.5):
        """
        Initializes a new instance of the animation class with specified parameters. 
        This constructor sets up the element type, animation names for entering and exiting, 
        and the duration of the animations.

        Args:
            element_type (str): The type of element to which the animation will be applied.
            animation_name_in (str): The name of the animation for the entry effect. Defaults to 'fadeIn'.
            animation_name_out (str): The name of the animation for the exit effect. Defaults to 'fadeOut'.
            duration (float): The duration of the animation in seconds. Defaults to 1.5.

        Returns:
            None

        """
        self.element_type = element_type
        self.animation_name_in = animation_name_in
        self.animation_name_out = animation_name_out
        self.duration = duration

    def generate_animation_classes(self, animation_name):
        """
        Generates CSS classes for animations based on the specified animation name and duration. 
        This method constructs the animation class and duration class strings, 
        which can be used to apply animations to elements in a user interface.

        Args:
            animation_name (str): The name of the animation to be applied.

        Returns:
            tuple: A tuple containing the animation class and the duration class.

        """
        # Generate the animation and duration classes
        animation_class = f'animate__{animation_name}'
        duration_class = f'custom-duration-{self.duration}s'
        return animation_class, duration_class

    def add_custom_css(self):
        """
        Adds custom CSS to the user interface for specifying animation duration. 
        This method generates a style block that sets the animation duration based 
        on the instance's duration attribute and injects it into the HTML head of the UI.

        Returns:
            None

        """
        # Add custom CSS for animation duration
        custom_css = f"""
        <style>
        .custom-duration-{self.duration}s {{
          animation-duration: {self.duration}s;
        }}
        </style>
        """
        ui.add_head_html(custom_css)

    def create_element(self, *args, **kwargs):
        """ Add class for in """
        self.add_custom_css()
        animation_class, duration_class = self.generate_animation_classes(self.animation_name_in)
        element = self.element_type(*args, **kwargs)
        element.classes(f'animate__animated {animation_class} {duration_class}')
        return element

    def delete_element(self, element):
        """ Add class for out and delete """
        animation_class, duration_class = self.generate_animation_classes(self.animation_name_out)
        element.classes(f'animate__animated {animation_class} {duration_class}')
        # Delay the actual deletion to allow the animation to complete
        ui.timer(self.duration, lambda: element.delete(), once=True)


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
