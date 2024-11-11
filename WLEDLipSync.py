# Compilation mode, standalone everywhere, except on macOS there app bundle
# nuitka-project-if: {OS} in ("Windows", "Linux", "FreeBSD"):
#    nuitka-project: --onefile
# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --standalone
#    nuitka-project: --macos-create-app-bundle
# nuitka-project-if: {OS} == "Windows":
#   nuitka-project: --onefile-windows-splash-screen-image={MAIN_DIRECTORY}/splash-screen.png
# nuitka-project-if: os.getenv("DEBUG_COMPILATION", "no") == "yes":
#   nuitka-project: --force-stdout-spec=WLEDVideoSync.out.txt
#   nuitka-project: --force-stderr-spec=WLEDVideoSync.err.txt
# nuitka-project-if: {OS} == "Linux":
#   nuitka-project: --include-module=gi
#   nuitka-project: --include-module=qtpy
# nuitka-project: --nofollow-import-to=doctest
# nuitka-project: --noinclude-default-mode=error
"""
a: zak-45
d: 09/10/2024
v: 1.0.0.0

Application to generate automatic Lip sync from a mp3 file.

File need to be split into two different audio files:
    1) vocals.mp3  (contains vocal part  only, will be automatically converted to wav for Rhubarb)
    2) accompaniment.mp3 for music only (optional)
    This can be done by using SpleeterGUI: https://github.com/zak-45/SpleeterGUI-Chataigne-Module
    or any other tool able to split music into stems.
    'vocals.mp3' can be also some self-recording voice done in any other way

Input files needs to be under ./media folder.
The structure is like that for song name e.g.: Mytest of all-time.mp3
./media/audio/Mytest of all-time
                |_vocals.mp3
                |_accompaniment.mp3

As output, this will generate a json file with corresponding time/mouth positions
./media/audio/Mytest of all-time
                |_WLEDLipSync.json
             +  |_vocals.wav <---- this one is used by rhubarb (external program) and created automatically if missing

For mouths model/images, need 9 images representing mouth positions:
./media/image/model/<model name>
                    |_A.png ... X.png

see: https://github.com/DanielSWolf/rhubarb-lip-sync

Send mouth cues to OSC and WS ...
Depend on how many mouth cues defined and if short interval, in some rare case, could miss letter during audio playback
    --> timeupdate frequency depend on several external factor , see HTML5 audio element doc
This is one of reason why actual letter and future one are sent on same message record.

09/10/2024 : there is a problem playing  file when refresh the browser : need investigation
"""
import json
import time
import cv2
import os
import sys
import asyncio
import utils
import logging
import concurrent_log_handler

from str2bool import str2bool
from OSCClient import OSCClient
from WSClient import WebSocketClient
from pathlib import Path
from PIL import Image
from nicegui import ui, app, native
from rhubarb import RhubarbWrapper
from niceutils import LocalFilePicker
from typing import List, Union

if sys.platform.lower() == 'win32':
    from asyncio import WindowsSelectorEventLoopPolicy, set_event_loop_policy

    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

rub = RhubarbWrapper()


"""
When this env var exist, this mean run from the one-file executable (compressed file).
Load of the config is not possible, folder config should not exist.
This avoid FileNotFoundError.
This env not exist when running from the decompressed program.
Expected way to work.
"""
if "NUITKA_ONEFILE_PARENT" not in os.environ:
    # read config
    # create logger
    logger = utils.setup_logging('config/logging.ini', 'WLEDLogger')

    # load config file
    lip_config = utils.read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key

    #  validate network config
    server_ip = server_config['server_ip']
    if not utils.validate_ip_address(server_ip):
        logger.error(f'Bad server IP: {server_ip}')
        sys.exit(1)

    server_port = server_config['server_port']

    if server_port == 'auto':
        server_port = native.find_open_port()
    else:
        server_port = int(server_config['server_port'])

    if server_port not in range(1, 65536):
        logger.error(f'Bad server Port: {server_port}')
        sys.exit(2)


class LipAPI:
    """
    Handles the lip synchronization API for audiovisual applications.

    This class manages the state and behavior of lip synchronization, including
    player status, mouth image buffers, and audio file properties. It provides
    functionality to manipulate and display mouth images based on audio cues.

    Attributes:
        player_status (str): Current status of the player.
        scroll_graphic (bool): Flag indicating if the graphic should scroll.
        mouth_times_buffer (dict): Buffer containing results from rhubarb.
        mouth_times_selected (list): List of selected mouth times.
        mouth_images_buffer (list): List of mouth images from a model.
        mouths_buffer_thumb (list): List of thumbnail mouth images.
        thumbnail_width (int): Width of thumbnail images.
        mouth_carousel: Carousel object for mouth images.
        mouth_area_h: Scroll area object for mouth display.
        audio_duration (float or None): Duration of the audio file.
        source_file (str): Path to the source audio file.
        output_file (str): Path to the output file.
        file_to_analyse (str): Path to the file to analyse.
        wave_show (bool): Flag indicating if the wave should be shown.
        mouth_cue_show (bool): Flag indicating if mouth cues should be shown.
        net_status_timer: Timer for network status.
        osc_client: OSC client for communication.
        wvs_client: WVS client for communication.
        data_changed (bool): Indicates if data has been changed by the user.
        preview_area: Area for displaying the model.

        mouth_to_image (dict): Mapping of mouth shapes to image indices.
    """

    player_status = ''
    scroll_graphic: bool = True
    mouth_times_buffer = {}  # buffer dict contains result from rhubarb
    mouth_times_selected = []  # list contain time selected
    mouth_images_buffer: List[cv2.Mat] = []  # list contains mouth images from a model
    mouths_buffer_thumb: List[cv2.Mat] = []  # contains thumb mouth images
    thumbnail_width: int = 64  # thumb image width
    # mouth_carousel: ui.carousel = None  # carousel object
    mouth_carousel = None  # carousel object
    mouth_area_h: Union[ui.scroll_area, None] = None  # scroll area object
    audio_duration: Union[float, None] = None  # audio file duration
    source_file = ''
    output_file = ''
    file_to_analyse = ''
    wave_show = True
    mouth_cue_show = True
    net_status_timer = None
    osc_client = None
    wvs_client = None
    data_changed = False  # True if some data has been changed by end user
    preview_area = None  # area where  display model

    mouth_to_image = {
        'A': 0,
        'B': 1,
        'C': 2,
        'D': 3,
        'E': 4,
        'F': 5,
        'G': 6,
        'H': 7,
        'X': 8
    }


async def load_image_async(img_path: str) -> cv2.Mat:
    """
    Loads an image asynchronously from the specified file path.

    This function reads an image file and converts its color format from BGR to RGB.
    It is designed to be used in an asynchronous context to avoid blocking the main thread.

    Args:
        img_path (str): The file path of the image to be loaded.

    Returns:
        cv2.Mat: The loaded image in RGB format, or None if the image could not be loaded.
    """

    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(None, cv2.imread, img_path, cv2.IMREAD_COLOR)
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


async def create_mouth_model(mouth_folder: str = './media/image/model/default'):
    """
    Loads mouth images from a specified folder into the LipAPI buffer.

    This function scans the given folder for image files, loads them asynchronously,
    and stores them in the LipAPI's mouth image buffers. It also checks if enough images
    have been loaded and triggers the creation of a carousel if successful.

    Args:
        mouth_folder (str): The path to the folder containing mouth images. Defaults to './media/image/model/default'.
    """

    LipAPI.mouth_images_buffer = []
    LipAPI.mouths_buffer_thumb = []

    logger.debug(mouth_folder)
    folder_path = Path(mouth_folder)
    supported_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')

    tasks = [
        load_image_async(str(img_path))
        for img_path in folder_path.iterdir()
        if img_path.suffix.lower() in supported_extensions and img_path.is_file()
    ]

    images = await asyncio.gather(*tasks)

    for img, img_path in zip(images, folder_path.iterdir()):
        if img is not None:
            LipAPI.mouth_images_buffer.append(img)
        else:
            logger.debug(f"Could not open image {img_path.name}: Image is None")

    if len(LipAPI.mouth_images_buffer) < 9:
        logger.debug(f'ERROR not enough images loaded into buffer: {len(LipAPI.mouth_images_buffer)}')
    else:
        logger.debug(f'Images loaded into buffer: {len(LipAPI.mouth_images_buffer)}')
        await create_carousel()



async def create_carousel():
    """
    Creates a carousel UI component for displaying mouth images.

    This function initializes a carousel with the mouth images stored in the LipAPI buffer,
    creating slides and thumbnails for each image. It also sets the default image to X.

    Returns:
        None
    """

    image_number = len(LipAPI.mouth_images_buffer)
    LipAPI.mouth_carousel = ui.carousel(animated=False, arrows=False, navigation=False)
    LipAPI.mouth_carousel.props('max-height=360px')
    with  LipAPI.mouth_carousel:
        for i in range(image_number):
            await create_carousel_slide(i)
            await create_thumbnail(i)

    # put to default image
    LipAPI.mouth_carousel.set_value(str(get_index_from_letter('X')))


async def create_carousel_slide(index: int):
    """Creates a carousel slide for displaying a mouth image.

    This function generates a slide in the carousel UI that displays a mouth image
    from the LipAPI's mouth_images_buffer at the specified index. It also includes
    an interactive button that shows the image dimensions and serves as a tooltip.

    Args:
        index (int): The index of the mouth image in the LipAPI's mouth_images_buffer.

    Returns:
        None
    """

    preview_slide = ui.carousel_slide(str(index))
    with preview_slide:
        carousel_image = Image.fromarray(LipAPI.mouth_images_buffer[index])
        h, w = LipAPI.mouth_images_buffer[index].shape[:2]
        img = ui.interactive_image(carousel_image.resize(size=(640, 360))).classes('w-[640]')
        with img:
            img_info = ui.button(text=f'{index}:{w}x{h}', icon='tag')
            img_info.props('flat fab').tooltip('Image Number')
            img_info.classes('absolute top-0 left-0 m-2')


async def create_thumbnail(index: int):
    """Creates a thumbnail image from the mouth images buffer.

    This function resizes a mouth image at the specified index to a thumbnail
    size while maintaining the aspect ratio. The resized thumbnail is then
    appended to the mouths buffer for later use.

    Args:
        index (int): The index of the mouth image in the LipAPI's mouth_images_buffer.

    Returns:
        None
    """

    image = LipAPI.mouth_images_buffer[index]
    height, width, _ = image.shape
    aspect_ratio = height / width
    new_height = int(LipAPI.thumbnail_width * aspect_ratio)
    resized_image = cv2.resize(image, (LipAPI.thumbnail_width, new_height))
    LipAPI.mouths_buffer_thumb.append(resized_image)


async def get_audio_duration(player: str = ''):
    """
    Get audio duration
    :param player: ID of the player object (str)
    :return: duration
    """

    return await ui.run_javascript(f'document.getElementById("{player}").duration;',timeout=2)


async def gen_thumbnails_from_array():
    """
    Generate thumbs from an array image
    this will take mouths_buffer and populate mouths_buffer_thumb
    Used to minimize time for page creation
    """

    for i in range(len(LipAPI.mouth_images_buffer)):
        image = LipAPI.mouth_images_buffer[i]
        # Resize the image to the specified thumbnail width while maintaining aspect ratio
        height, width, _ = image.shape
        aspect_ratio = height / width
        new_height = int(LipAPI.thumbnail_width * aspect_ratio)
        resized_image = cv2.resize(image, (LipAPI.thumbnail_width, new_height))
        LipAPI.mouths_buffer_thumb.append(resized_image)  # add to list


def get_index_from_letter(letter):
    """
    Return the index associated with the given letter.

    This function retrieves the index corresponding to a specified letter
    from the LipAPI's mouth_to_image mapping. If the letter is not found,
    it returns a default index of 8.

    Args:
        letter (str): The letter for which to find the corresponding index.

    Returns:
        int: The index associated with the given letter, or 8 if the letter is not found.
    """

    return LipAPI.mouth_to_image.get(letter, 8)


def get_letter_from_index(ndx):
    """
    Return the letter associated with the given index.

    This function retrieves the letter corresponding to the specified index
    from the LipAPI's mouth_to_image mapping. If the index does not correspond
    to any letter, it returns 'X' as a default value.

    Args:
        ndx (int): The index for which to find the corresponding letter.

    Returns:
        str: The letter associated with the given index, or 'X' if not found.
    """

    return next(
        (
            i
            for i in LipAPI.mouth_to_image
            if LipAPI.mouth_to_image.get(i) == ndx
        ),
        'X',
    )


def save_data(force: bool = False):
    """
    Saves the current mouth times buffer to a JSON file.

    This function checks if there are changes to be saved and prompts the user
    with a dialog to confirm saving the data. If confirmed, it writes the mouth
    times buffer to a specified output file in JSON format.

    Args:
        force (bool): If True, forces the save operation regardless of whether
                      there are changes. Defaults to False.

    Returns:
        None
    """

    def run_it():
        with open(f'{LipAPI.output_file}.json', 'w', encoding='utf-8') as f:
            json.dump(LipAPI.mouth_times_buffer, f, ensure_ascii=False, indent=4)
            LipAPI.data_changed = False
        dialog.close()

    if LipAPI.output_file != '' and (LipAPI.data_changed is True or force):
        with ui.dialog() as dialog, ui.card():
            dialog.open()
            with ui.row():
                ui.button('save changes to file', on_click=run_it)
                ui.button('Exit', on_click=dialog.close)
    else:
        ui.notify('nothing to do')


async def edit_mouth_time_buffer():
    """
    Opens a dialog for editing the mouth times buffer.

    This function allows users to modify the mouth times buffer, which is populated
    from an output file generated by audio analysis. If the buffer contains data,
    a JSON editor is displayed for editing, along with options to save changes or exit.

    Returns:
        None
    """

    def on_change(event):
        LipAPI.mouth_times_buffer = event.content['json']

    if len(LipAPI.mouth_times_buffer) > 0:
        with ui.card():
            ui.json_editor({'content': {'json': LipAPI.mouth_times_buffer}}, on_change=on_change)
            with ui.row():
                ui.button(icon='save', on_click=lambda: save_data(force=True))

    else:
        ui.notification('Nothing to edit... Maybe load/reload mouth data cue', position='center', type='warning')


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


@ui.page('/')
async def main_page():
    """
    Initializes the main page of the application.

    This function sets up the user interface for the main page, including audio
    controls, network status checks, and the ability to load and manage mouth cues.
    It also handles the initialization of various components and their interactions.

    Returns:
        None
    """

    async def set_audio_duration():
        """
        Updates the audio duration for the vocal player.

        This function loads the audio element for the vocal player and retrieves
        its current duration, storing it in the LipAPI's audio_duration attribute.

        Returns:
            None
        """

        LipAPI.audio_duration = await get_audio_duration('player_vocals')

    async def check_net_status():
        """
        Checks the network status of OSC and WVS clients.

        This function verifies the connectivity of the OSC and WVS clients by checking
        the status of their respective network ports. It updates the UI elements to reflect
        the current connection status and stops the WVS client if it is not connected.

        Returns:
            None
        """

        logger.debug('net check status')

        if LipAPI.osc_client is not None:
            # check net status UDP port, can provide false positive
            result = await utils.check_udp_port(ip_address=osc_ip.value, port=int(osc_port.value))
            if result is True:
                # set value depend on return code
                link_osc.props(remove="color=yellow")
                link_osc.props(add="color=green")

            else:
                link_osc.props(remove="color=green")
                link_osc.props(add="color=yellow")

        if LipAPI.wvs_client is not None:
            # check net status, TCP port
            result = await utils.check_ip_alive(ip_address=wvs_ip.value, port=int(wvs_port.value))
            if result is True:
                # set value depend on return code
                link_wvs.props(remove="color=yellow")
                link_wvs.props(add="color=green")
            else:
                link_wvs.props(remove="color=green")
                link_wvs.props(add="color=yellow")
                LipAPI.wvs_client.stop()
                LipAPI.wvs_client = None

        if wvs_activate.value is False and osc_activate.value is False:
            link_wvs.props(remove="color=green")
            link_wvs.props(remove="color=yellow")
            link_osc.props(remove="color=yellow")
            link_osc.props(remove="color=green")
            LipAPI.net_status_timer.active = False

    async def manage_wvs_client():
        """
        Manages the WebSocket client for WVS activation and deactivation.

        This function activates the WVS client if the corresponding toggle is enabled,
        creating a new WebSocket connection if one does not already exist. It also sends
        an initialization message and manages the network status timer, stopping the client
        if the toggle is disabled.

        Returns:
            None
        """

        logger.debug('WVS activation')

        if wvs_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.wvs_client is None:
                ws_address = "ws://" + str(wvs_ip.value) + ":" + str(int(wvs_port.value)) + str(wvs_path.value)
                LipAPI.wvs_client = WebSocketClient(ws_address)
                LipAPI.wvs_client.run()
                # check until connected timeout 1 s
                nb = 0
                while LipAPI.wvs_client.get_status() != 'connected':
                    await asyncio.sleep(0.1)
                    if nb > 9:
                        logger.debug('error to connect to ws')
                        return
                    nb += 1
            # send init message
            wvs_msg = {"action":{"type":"init_wvs","param":{"metadata":"","mouthCues":""}}}
            # add metadata if requested
            if wvs_send_metadata.value is True:
                wvs_msg = {"action": {"type": "init_wvs", "param": LipAPI.mouth_times_buffer}}
                wvs_send_metadata.value = False
            LipAPI.wvs_client.send_message(wvs_msg)
            # create or activate net timer
            if LipAPI.net_status_timer is None:
                LipAPI.net_status_timer = ui.timer(5, check_net_status)
            else:
                LipAPI.net_status_timer.active = True

        else:
            # we stop the client
            if LipAPI.wvs_client is not None:
                LipAPI.wvs_client.stop()
            LipAPI.wvs_client = None
            link_wvs.props(remove="color=green")
            link_wvs.props(remove="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.net_status_timer.active is True and osc_activate.value is False:
                logger.debug('stop timer')
                LipAPI.net_status_timer.active = False

    async def manage_osc_client():
        """
        Manages the OSC client for activation and deactivation.

        This function activates the OSC client if the corresponding toggle is enabled,
        creating a new OSC client connection if one does not already exist. It sends an
        initialization message and manages the network status timer, stopping the client
        if the toggle is disabled.

        Returns:
            None
        """

        logger.debug('OSC activation')

        if osc_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.osc_client is None:
                LipAPI.osc_client = OSCClient(str(osc_ip.value), int(osc_port.value))
            # send init message
            osc_msg = {"action":{"type":"init_osc","param":{}}}
            if osc_send_metadata.value is True:
                osc_msg = {"action": {"type": "init_osc", "param": LipAPI.mouth_times_buffer}}
                osc_send_metadata.value = False
            LipAPI.osc_client.send_message(osc_address.value, osc_msg)
            # create or activate net timer
            if LipAPI.net_status_timer is None:
                LipAPI.net_status_timer = ui.timer(5, check_net_status)
            else:
                LipAPI.net_status_timer.active = True

        else:
            # we stop the client
            if LipAPI.osc_client is not None:
                LipAPI.osc_client.stop()
            LipAPI.osc_client = None
            link_osc.props(remove="color=green")
            link_osc.props(remove="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.net_status_timer.active is True and wvs_activate.value is False:
                logger.debug('stop timer')
                LipAPI.net_status_timer.active = False

    def validate_file(file_name):
        """ file input validation """

        # disable button
        load_mouth_button.disable()
        edit_mouth_button.disable()

        # check some requirements
        if file_name == '':
            ui.notify('Blank value not allowed')
            return False
        elif not file_name.lower().endswith('.mp3'):
            ui.notify('Only MP3')
            return False
        elif not os.path.isfile(file_name):
            ui.notify(f'File {file_name} does not exist')
            return False

        return True

    async def approve_set_file_name():
        """ dialog to approve load new audio file """

        async def run_it():
            if LipAPI.data_changed is True:
                ui.notification('Changed data has been detected, you need to save before or refresh to bypass',
                                position='center', type='info', timeout=10, close_button=True)
            else:
                dialog.close()
                await set_file_name()

        with ui.dialog() as dialog, ui.card():
            dialog.open()
            ui.label(f'Load {audio_input.value} ....')
            ui.label('Are you sure ? ')
            with ui.row():
                ui.button('Yes', on_click=run_it)
                ui.button('No', on_click=dialog.close)

    async def set_file_name():
        """
        set file name from file input audio
        check if corresponding media entries exist
        """

        def file_alone():
            """ no stems """
            ui.notify(f'Analysis done from audio source file {file_name}.')
            out = 'output/' + file + '.json'
            if os.path.isfile(out):
                ui.notify(f'Found an already analysis file ...  {out}.')
            # convert mp3 to wav
            utils.convert_audio(file_path, file_folder + file + '.wav')
            player_vocals.set_source(file_path)
            LipAPI.file_to_analyse = file_folder + file + '.wav'

        #  set some init value
        player_vocals.seek(0)
        player_accompaniment.seek(0)
        spinner_accompaniment.set_visibility(False)
        spinner_vocals.set_visibility(False)
        LipAPI.mouth_times_buffer = {}
        LipAPI.mouth_times_selected = []
        try:
            LipAPI.mouth_area_h.delete()
        except AttributeError:
            pass
        except  ValueError:
            pass

        # file to check
        file_path = audio_input.value
        # case where browser refresh
        if LipAPI.source_file != '' and audio_input.value == '':
            file_path = LipAPI.source_file
        # main file checks
        if validate_file(file_path):
            # extract file name only
            file_name = os.path.basename(file_path)
            file_info = os.path.splitext(file_name)
            file = file_info[0]
            file_folder = './media/audio/' + file + '/'

            # check if folder not exist
            if not os.path.isdir(file_folder):
                ui.notify(f'folder {file_folder} does not exist, creating ...')
                os.mkdir(file_folder)
                # in this case, source file is supposed to be only vocal, but not mandatory
                file_alone()
                ui.timer(1, set_audio_duration, once=True)

            else:
                # check if both mp3 files exist, if not so suppose not stems, manage from only source file
                if not os.path.isfile(file_folder + 'accompaniment.mp3') or \
                        not os.path.isfile(file_folder + 'vocals.mp3'):

                    file_alone()

                else:
                    # stems
                    ui.notify('We will do analysis from stems files ...')
                    # specific case for vocals
                    if not os.path.isfile(file_folder + 'vocals.wav'):
                        # generate wav from mp3
                        utils.convert_audio(file_folder + 'vocals.mp3', file_folder + 'vocals.wav')
                        ui.notify('auto generate wav file')

                        # double check
                        if not os.path.isfile(file_folder + 'vocals.wav'):
                            ui.notification('ERROR on wav file creation', position='center', type='negative')
                            player_vocals.set_source('')
                            LipAPI.audio_duration = None
                            return

                    # set players
                    player_vocals.set_source(file_folder + 'vocals.mp3')
                    # this one is optional
                    player_accompaniment.set_source(file_folder + 'accompaniment.mp3')
                    LipAPI.file_to_analyse = file_folder + 'vocals.wav'

            # set params
            LipAPI.source_file = audio_input.value
            LipAPI.output_file = 'output/' + file
            edit_mouth_button.enable()
            load_mouth_button.enable()
            ui.timer(1, set_audio_duration, once=True)

        else:

            audio_input.set_value('')

    async def pick_file_to_analyze() -> None:
        """ Select file to analyse """

        result = await LocalFilePicker('./', multiple=False)
        ui.notify(f'Selected :  {result}')

        if result is not None:
            if sys.platform.lower() == 'win32' and len(result) > 0:
                result = str(result[0]).replace('\\', '/')
            if len(result) > 0:
                result = './' + result
            if validate_file(result):
                audio_input.value = result

    def analyse_audio():
        """
        Initiates the audio analysis process using the Rhubarb tool.

        This function prompts the user for confirmation before running the audio analysis
        on the specified source file. It checks for various conditions such as whether an
        analysis is already running, if the data has changed, or if the source file is set,
        and updates the UI accordingly during the analysis process.

        Args:

        Returns:
            None
        """

        def run_it():
            if rub._instance_running:
                ui.notification('Already running instance', type='negative', position='center')
            elif LipAPI.data_changed is True:
                ui.notification('You have changed some data ....run not allowed',
                                position='center', close_button=True, type='warning', timeout=10)
            elif LipAPI.file_to_analyse == '':
                ui.notification('Source file not set ', type='negative', position='center')
            else:
                if rub.return_code > 0:
                    ui.notification('Caution ...Last running instance in trouble', type='negative', position='center')
                ui.notify('Audio Analysis initiated')

                # run analyzer
                rub.run(file_name=LipAPI.file_to_analyse, output=LipAPI.output_file)

                # set some GUI
                spinner_analysis.set_visibility(True)
                player_vocals.pause()
                player_accompaniment.pause()
                spinner_accompaniment.set_visibility(False)
                spinner_vocals.set_visibility(False)
                load_model_button.disable()
                edit_mouth_button.disable()
                load_mouth_button.disable()
                ok_button.disable()
                try:
                    LipAPI.mouth_area_h.delete()
                except ValueError:
                    pass
                except AttributeError:
                    pass
                LipAPI.mouth_times_buffer = {}
                LipAPI.mouth_times_selected = []
                dialog.close()

        with ui.dialog() as dialog, ui.card():
            dialog.open()
            ui.label(f'Analyse file "{LipAPI.source_file}" with Rhubarb')
            ui.label(f'This will overwrite : {LipAPI.output_file}.json')
            ui.label('Are You Sure ?')
            with ui.row():
                ui.button('Yes', on_click=run_it)
                ui.button('No', on_click=dialog.close)

    async def load_mouth_cue():
        """ initiate mouth card cue creation """

        def run_it():

            if LipAPI.data_changed is True:
                dialog.close()

            try:
                LipAPI.mouth_area_h.delete()
            except ValueError:
                pass
            except AttributeError:
                pass

            LipAPI.mouth_times_buffer = {}
            LipAPI.mouth_times_selected = []

            if LipAPI.source_file != '':
                ui.notification('this could take some times .....', position='center', type='warning', spinner=True)

                if os.path.isfile(LipAPI.output_file + '.json'):
                    with open(LipAPI.output_file + '.json', 'r') as data:
                        LipAPI.mouth_times_buffer = json.loads(data.read())

                    ui.timer(1, generate_mouth_cue, once=True)

                else:
                    ui.notify('No analysis file to read')
            else:
                ui.notify('Source file blank ... load a new file')

        if LipAPI.data_changed is True:
            with ui.dialog() as dialog, ui.card():
                dialog.open()
                ui.label(f'Detected changed data ...')
                ui.label('Are You Sure ?')
                with ui.row():
                    ui.button('Yes', on_click=run_it)
                    ui.button('No', on_click=dialog.close)
        else:
            run_it()

    async def load_mouth_model():
        """ load images from model folder into a carousel """

        result = await LocalFilePicker('./media/image/model', multiple=False)

        ui.notify(f'Selected :  {result}')

        if result is not None:
            if os.path.isdir(result[0]):
                if sys.platform.lower() == 'win32' and len(result) > 0:
                    result = str(result[0]).replace('\\', '/')
                if len(result) > 0:
                    result = './' + result
                    # delete if exist
                    try:
                        LipAPI.mouth_carousel.delete()
                    except ValueError:
                        pass
                    # generate new one
                    await create_mouth_model(result)
                    # move it to selected container
                    LipAPI.mouth_carousel.move(target_container=LipAPI.preview_area)

            else:
                logger.debug('you need to select folder')

    def find_actual_nearest_cue_point(time_cue, cue_points):
        """ find mouth card near provided time """

        if not cue_points or 'mouthCues' not in cue_points:
            return [{"start": None, "end": None, "value": None},{"start": None, "end": None, "value": None}]

        threshold = 5
        actual_cue = {"start": None, "end": None, "value": None}
        nearest_cue = {"start": None, "end": None, "value": None}
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

    def add_all_markers():
        """ run java to add all markers """

        ui.run_javascript(f'LoadMouthCues("{LipAPI.output_file}.json");', timeout=5)


    async def modify_letter(start_time, letter_lbl):
        """ create letter modification dialog and update """

        def upd_letter(new_letter):
            """ update label and buffer """
            for cue in LipAPI.mouth_times_buffer['mouthCues']:
                if cue['start'] == start_time:
                    cue['value'] = new_letter
                    letter_lbl.style(add='color:orange')
                    LipAPI.data_changed = True
                    logger.debug(f'new letter set {new_letter}')
                    break

            letter_lbl.text = new_letter
            dialog.close()

        with ui.dialog() as dialog, ui.card():
            """ dialog for letter update """

            dialog.open()
            ui.label(f'Modify letter : {letter_lbl.text}')
            # retrieve thumb image from ndx
            ui.image(Image.fromarray(LipAPI.mouths_buffer_thumb[get_index_from_letter(letter_lbl.text)]))

            # read thumb array, images from 0  to x...(usually 9)
            i = 0
            for img_array in LipAPI.mouths_buffer_thumb:
                img = Image.fromarray(img_array)
                with ui.row():
                    ui.interactive_image(img).classes('w-10')
                    # retrieve letter from index
                    img_letter = get_letter_from_index(i)
                    # create corresponding checkbox
                    ui.checkbox(img_letter, on_change=lambda e=img_letter: upd_letter(e))
                    i += 1

    async def generate_mouth_cue():
        """Generate graphical view of json file, could be time-consuming if display thumbs."""

        async def select_letter(start_time: float, letter_lbl: ui.label):
            logger.debug(start_time, letter_lbl)
            await modify_letter(start_time, letter_lbl)

        def position_player(seek_time: float, card: ui.card, rem: ui.icon, marker: str = 'X'):
            """Set players to the specified time."""
            player_vocals.seek(seek_time)
            player_accompaniment.seek(seek_time)
            if seek_time not in LipAPI.mouth_times_selected:
                LipAPI.mouth_times_selected.append(seek_time)
                LipAPI.mouth_times_selected.sort()
            create_marker(seek_time,marker)
            card.classes(remove='bg-cyan-700')
            card.classes(add='bg-red-400')
            rem.set_visibility(True)
            card.update()

        async def play_until(start_time: float):
            player_vocals.seek(start_time)
            end_cue = next((cue for cue in LipAPI.mouth_times_selected if cue > start_time), LipAPI.audio_duration)
            duration = end_cue - start_time
            end_time = time.time() + duration
            player_vocals.play()

            while time.time() <= end_time:
                await asyncio.sleep(0.001)

            player_vocals.pause()
            logger.debug('End of play_until loop.')

        def set_default(seek_time: float, card: ui.card, rem: ui.icon):
            """Reset time card to default color."""
            LipAPI.mouth_times_selected.remove(seek_time)
            card.classes(remove='bg-red-400')
            card.classes(add='bg-cyan-700')
            rem.set_visibility(False)
            card.update()
            logger.debug(LipAPI.mouth_times_selected)

        # Scroll area with timeline/images
        LipAPI.mouth_area_h = ui.scroll_area().classes('bg-cyan-700 w-400 h-40')
        LipAPI.mouth_area_h.props('id="CuePointsArea"')
        LipAPI.mouth_area_h.bind_visibility(LipAPI, 'mouth_cue_show')
        with LipAPI.mouth_area_h:
            all_rows_mouth_area_h = ui.row(wrap=False)
            all_rows_mouth_area_h.props('id=CuePoints')
            with all_rows_mouth_area_h:
                if len(LipAPI.mouth_images_buffer) == 9 and 'mouthCues' in LipAPI.mouth_times_buffer:
                    mouth_cues = LipAPI.mouth_times_buffer['mouthCues']
                    for cue in mouth_cues:
                        start = cue['start']
                        letter = cue['value']
                        time_card = ui.card().classes(add="bg-cyan-700 cue-point")
                        time_card.props(f'id={start}')
                        with time_card:
                            ic_remove = ui.icon('highlight_off', size='xs').style(add='cursor: pointer')
                            ic_remove.on('click',
                                         lambda st=start, card=time_card, rem=ic_remove: set_default(st, card, rem))
                            ic_remove.set_visibility(False)

                            start_label = ui.label(start)
                            start_label.on('click',
                                           lambda st=start, card=time_card, rem=ic_remove, lb=letter: position_player(st, card,
                                                                                                           rem, lb))
                            start_label.tooltip('Click to set player time')
                            start_label.style('cursor:grab')

                            ic_play = ui.icon('play_circle', size='xs').style(add='cursor: pointer')
                            ic_play.on('click', lambda st=start: play_until(st))

                        letter_label = ui.label(letter).style('cursor:pointer')
                        letter_label.on('click', lambda st=start, lb=letter_label: select_letter(st, lb))

        # Move to the right container
        LipAPI.mouth_area_h.move(target_container=card_mouth)

        # This could take some time
        ui.timer(1, run_gencuedata, once=True)

        LipAPI.data_changed = False
        edit_mouth_button.enable()
        load_mouth_button.enable()

    async def get_player_time():
        """
        get player current playing time
        """

        current_play_time = round(await ui.run_javascript("document.getElementById('player_vocals').currentTime;", timeout=3),2)

        return current_play_time

    async def player_time_action():
        """
        Set scroll area position
        Send WVS / OSC msg
        """

        play_time = await get_player_time()

        actual_cue_record, next_cue_record = find_actual_nearest_cue_point(play_time, LipAPI.mouth_times_buffer)
        letter = next_cue_record['value']

        # if time zero hide spinner
        if play_time == 0:
            spinner_vocals.set_visibility(False)
        else:
            if LipAPI.player_status == 'play':
                spinner_vocals.set_visibility(True)

        # send osc message
        if osc_activate.value is True and (LipAPI.player_status == 'play' or send_seek.value is True):
            LipAPI.osc_client.send_message(osc_address.value + '/mouthCue/',
                                           ["{:.3f}".format(play_time),
                                            actual_cue_record['value'],
                                            next_cue_record['start'],
                                            next_cue_record['end'], letter])

        # send wvs message
        if wvs_activate.value is True and (LipAPI.player_status == 'play' or send_seek.value is True):
            ws_msg = {"action":{"type":"cast_image",
                                "param":{"image_number":get_index_from_letter(actual_cue_record['value']),
                                         "device_number":0,
                                         "class_name":"Media",
                                         "fps_number":100,
                                         "duration_number":10}}}
        
            LipAPI.wvs_client.send_message(ws_msg)

        # set new value to central label
        new_label = (str(play_time) + ' | ' +
                     str(actual_cue_record['value'])+
                     ' | ' +
                     str(letter) +
                     ' - ' +
                     str(get_index_from_letter(letter)))
        time_label.set_text(new_label)

        # set the index image in carousel (letter)
        if LipAPI.mouth_carousel is not None:
            LipAPI.mouth_carousel.set_value(str(get_index_from_letter(actual_cue_record['value'])))

        # scroll central mouth cues
        if LipAPI.player_status == 'play' and LipAPI.scroll_graphic is True:
            if LipAPI.audio_duration is None:
                LipAPI.audio_duration = await get_audio_duration('player_vocals')
            if LipAPI.mouth_area_h is not None:
                LipAPI.mouth_area_h.scroll_to(percent=((play_time * 100) / LipAPI.audio_duration) / 100,
                                              axis='horizontal')

    def update_progress(data, is_stderr):
        """
        Update the progress of an ongoing analysis based on the provided data.

        This function checks if the data incoming from an error stream and updates
        the progress circular indicator accordingly. When the analysis is complete,
        it makes certain UI elements visible or enabled to indicate that the process
        has finished.

        update circular progress when rhubarb working
        Caution: no ui action here, run from background ?????

        Args:
            data (dict): A dictionary containing progress information, which may include a 'value' key.
            is_stderr (bool): A flag indicating whether the data is from the standard error stream.

        Returns:
            None
        """
        
        if is_stderr and 'value' in data:
            new_value = data['value']
            circular.set_value(new_value)
            if new_value == 1:
                spinner_analysis.set_visibility(False)
                load_model_button.enable()
                edit_mouth_button.enable()
                load_mouth_button.enable()
                ok_button.enable()
                logger.debug('Analysis Finished')

    async def sync_player(action):
        """ sync players """

        if action == 'play':
            player_vocals.play()
            player_accompaniment.play()
        elif action == 'pause':
            player_vocals.pause()
            player_accompaniment.pause()
        elif action == 'sync':
            play_time = await get_player_time()
            player_accompaniment.seek(play_time)

    def event_player_vocals(event):
        """ store player status to class attribute """

        if event == 'end':
            LipAPI.player_status = 'end'
            spinner_vocals.set_visibility(False)

        elif event == 'play':
            LipAPI.player_status = 'play'
            # ui.notify('Playing audio')
            spinner_vocals.set_visibility(True)

        elif event == 'pause':
            LipAPI.player_status = 'pause'
            # ui.notify('Player on pause')
            if rub._instance_running is False:
                spinner_vocals.set_visibility(True)

    def event_player_accompaniment(event):
        """ action from player accompanied """

        if event == 'end':
            spinner_accompaniment.set_visibility(False)

        elif event == 'play':
            spinner_accompaniment.set_visibility(True)

        elif event == 'pause':
            spinner_accompaniment.set_visibility(False)

    async def audio_edit():
        """
        Opens an audio editing dialog with an embedded editor.

        This function prepares the audio file path for editing and displays a dialog
        containing an iframe that loads the audio editing interface. It also provides
        buttons for opening the editor in a new tab or closing the dialog.
        Will load the iframe by passing the working audio file (mp3 format) as URL parameter.

        Args:
        Returns:
            None
        """

        audiomass_file = LipAPI.file_to_analyse.replace('.wav','.mp3')
        audiomass_file = audiomass_file.replace('./','/')
        # http://yourdomain.com/index.html?yourParam=exampleValue

        dialog = ui.dialog() \
                .props(add='full-width full-height transition-show="slide-up" transition-hide="slide-down"')

        with dialog:
            dialog.open()
            editor_card = ui.card().classes('w-full')
            with editor_card:
                ui.html(f'''                
                <iframe src="audiomass/src/index.html?WLEDLipSyncFilePath={audiomass_file}" frameborder="0" 
                style="overflow:hidden;overflow-x:hidden;overflow-y:hidden;
                        height:100%;width:100%;
                        position:absolute;top:0px;left:0px;right:0px;bottom:0px" 
                height="100%" width="100%">
                </iframe>
                ''')
                with ui.page_sticky(position='top-right', x_offset=25, y_offset=25):
                    with ui.row():
                        new_editor = ui.button(icon='edit',color='yellow')
                        new_editor.on('click', lambda :ui.navigate.to('/audiomass', new_tab=True))
                        new_editor.props(add='round outline size="8px"')
                        new_editor.tooltip('Open editor in new tab')
                        close = ui.button(icon='close',color='red')
                        close.on('click', lambda :dialog.close())
                        close.props(add='round outline size="8px"')
                        close.tooltip('Close editor')


    async def mouth_time_buffer_edit():

        dialog = ui.dialog() \
                .props(add='full-width full-height transition-show="slide-up" transition-hide="slide-down"')

        with dialog:
            dialog.open()
            editor_card = ui.card().classes('w-full')
            with editor_card:
                ui.html(f'''                
                <iframe src="/edit" frameborder="0" 
                style="overflow:hidden;overflow-x:hidden;overflow-y:hidden;
                        height:100%;width:100%;
                        position:absolute;top:0px;left:0px;right:0px;bottom:0px" 
                height="100%" width="100%">
                </iframe>
                ''')
                with ui.page_sticky(position='top-right', x_offset=25, y_offset=25):
                    with ui.row():
                        new_editor = ui.button(icon='edit',color='yellow')
                        new_editor.on('click', lambda :ui.navigate.to('/edit', new_tab=True))
                        new_editor.props(add='round outline size="8px"')
                        new_editor.tooltip('Open editor in new tab')
                        close = ui.button(icon='close',color='red')
                        close.on('click', lambda :dialog.close())
                        close.props(add='round outline size="8px"')
                        close.tooltip('Close editor')


    # reset to default at init
    LipAPI.data_changed = False
    #
    # Rhubarb instance, callback will send back two values: data and is_stderr (for STDErr capture)
    #
    rub.callback = update_progress

    #
    # Main UI generation
    #
    utils.apply_custom()
    #
    card_top_preview = ui.card(align_items='center').tight().classes('no-shadow no-border w-full h-1/3')
    card_top_preview.set_visibility(False)

    with ui.row(wrap=False).classes('w-full'):

        card_left_preview = ui.card(align_items='center').tight().classes('self-center no-shadow no-border w-1/3')
        card_left_preview.set_visibility(False)

        card_left = ui.card().tight().classes('w-full')
        card_left.set_visibility(True)
        with card_left:
            card_mouth = ui.card().classes('w-full')
            card_mouth.props('id="CardMouth"')
            with card_mouth:
                with ui.row():
                    ic_save = ui.icon('save')
                    ic_save.on('click', lambda: save_data())
                    output_label = ui.label('Output')
                    output_label.bind_text_from(LipAPI, 'output_file')
                    ui.label('.json')
                    ic_refresh = ui.icon('refresh')
                    ic_refresh.on('click', lambda: ui.navigate.to('/'))
                    file_label = ui.label('File Name')
                    file_label.bind_text_from(LipAPI, 'source_file')
            with ui.row():

                del_markers = ui.chip('Clear', icon='clear', color='red', on_click=lambda :clear_markers())
                del_markers.tooltip('clear all markers')
                del_markers.bind_visibility(LipAPI,'wave_show')
                add_markers = ui.chip('Add', icon='add', color='red', on_click=lambda :add_all_markers())
                add_markers.tooltip('Add all markers')
                add_markers.bind_visibility(LipAPI,'wave_show')
                ui.chip('Audio Editor', icon='edit', text_color='yellow', on_click=lambda: audio_edit())
                ui.label('').bind_text_from(LipAPI,'file_to_analyse')

            waveform = ui.html('''
            <div id=waveform ><div>
            ''')
            waveform.classes('w-full h-full')
            waveform.bind_visibility(LipAPI, 'wave_show')

            zoom = ui.html('''
                <p>
                  <label style="margin-left: 2em">
                    Zoom: <input type="range" min="1" max="1000" value="1" />
                  </label>
                </p>
            ''')
            zoom.bind_visibility(LipAPI, 'wave_show')

            # time info
            with ui.row(wrap=False).classes('self-center'):
                ui.icon('watch', size='xs')
                time_label = ui.label('0.0 X 0').classes('self-center')
                time_label.style('margin:5px;'
                                 'padding:5px;'
                                 'font-size:20px;'
                                 'color:yellow;'
                                 'background:#164E63;'
                                 'width:260px;'
                                 'text-align:center')

                if len(LipAPI.mouths_buffer_thumb) > 0:
                    model_img = Image.fromarray(LipAPI.mouths_buffer_thumb[0])
                    ui.image(model_img).classes('w-6')

            with ui.row().classes('self-center'):
                ui.separator()

                with ui.column():
                    # player for vocals part, better mp3 file
                    player_vocals = ui.audio('').props('id=player_vocals')
                    player_vocals.props('preload=auto')
                    player_vocals.on('timeupdate', lambda: player_time_action())
                    player_vocals.on('play', lambda: event_player_vocals('play'))
                    player_vocals.on('pause', lambda: event_player_vocals('pause'))
                    player_vocals.on('ended', lambda: event_player_vocals('end'))
                    spinner_vocals = ui.spinner('audio', size='lg', color='green')
                    spinner_vocals.set_visibility(False)
                    ui.label('VOCALS').classes('self-center')

                # card area center
                control_area_v = ui.card(align_items='center').classes('w-44 h-60 border bg-cyan-900')
                with control_area_v:
                    spinner_analysis = ui.spinner('dots', size='sm', color='red')
                    spinner_analysis.set_visibility(False)
                    with ui.row(wrap=False):
                        circular = ui.circular_progress()
                        run_icon = ui.icon('rocket', size='lg')
                        run_icon.style('cursor: pointer')
                        run_icon.tooltip('Click to analyse audio with Rhubarb')
                        run_icon.on('click', lambda: analyse_audio())
                        scroll_time = ui.checkbox('')
                        scroll_time.tooltip('check to auto scroll graphic mouth cue')
                        scroll_time.bind_value(LipAPI, 'scroll_graphic')
                    with ui.row():
                        ui.button(on_click=lambda: sync_player('play'), icon='play_circle').props('outline')
                        ui.button(on_click=lambda: sync_player('pause'), icon='pause_circle').props('outline')
                    sync_player_button = ui.button(on_click=lambda: sync_player('sync'), icon='sync')
                    sync_player_button.classes('w-10')
                    sync_player_button.props('outline')
                    with ui.row() as net_row:
                        ui.label('WVS')
                        link_wvs = ui.icon('link', size='xs')
                        link_osc = ui.icon('link', size='xs')
                        ui.label('OSC')

                # player 2
                with ui.column():
                    # player for musical part, need mp3 file
                    player_accompaniment = ui.audio('').props('id=player_accompaniment')
                    spinner_accompaniment = ui.spinner('audio', size='lg', color='green')
                    player_accompaniment.on('play', lambda: event_player_accompaniment('play'))
                    player_accompaniment.on('pause', lambda: event_player_accompaniment('pause'))
                    player_accompaniment.on('ended', lambda: event_player_accompaniment('end'))
                    spinner_accompaniment.set_visibility(False)
                    ui.label('ACCOMPANIMENT').classes('self-center')

            ui.separator()

            with ui.row():
                folder = ui.icon('folder', size='md', color='yellow')
                folder.style(add='cursor: pointer')
                # made necessary checks
                folder.on('click', lambda: pick_file_to_analyze())
                # Add an input field for the audio file name
                audio_input = ui.input(placeholder='Audio file to analyse', label='Audio File Name')
                audio_input.on('focusout', lambda: validate_file(audio_input.value))
                # Add an OK button to refresh the waveform and set all players and data
                ok_button = ui.button('OK', on_click=approve_set_file_name)
                ui.checkbox('Wave').bind_value(LipAPI, 'wave_show')
                ui.checkbox('MouthCue').bind_value(LipAPI, 'mouth_cue_show')

            ui.label(' ')

            with ui.row():
                load_mouth_button = ui.button('Load MouthCue', on_click=load_mouth_cue)
                load_mouth_button.disable()
                edit_mouth_button = ui.button('Edit mouth Buffer',
                                              on_click=mouth_time_buffer_edit)
                edit_mouth_button.disable()
                load_model_button = ui.button('Load a model', on_click=load_mouth_model)

        with ui.card(align_items='center').tight().classes(
                'self-center no-shadow no-border w-1/3') as card_right_preview:
            LipAPI.preview_area = card_right_preview
            # generate default mouth model on first run
            if len(LipAPI.mouth_images_buffer) == 0:
                await create_mouth_model()
            card_right_preview.set_visibility(False)

    # button for right menu show/hide
    with ui.page_sticky(position='top-right', y_offset=10):
        ui.button(on_click=lambda: right_drawer.toggle(), icon='menu').props('flat')

    # right slide menu
    with ui.right_drawer(fixed=False).classes('bg-cyan-700').props('bordered') as right_drawer:

        right_drawer.hide()
        ui.label('SETTINGS')

        with ui.row(wrap=False):
            dark = ui.dark_mode()
            ui.switch('dark mode', on_change=dark.toggle)
            ui.switch('Show', on_change=lambda v: card_left.set_visibility(v.value), value=True)

        with ui.card(align_items='center').tight().classes('bg-cyan-400'):
            # Function to move the carousel to the desired target container
            def move_preview(container):
                def run_it():
                    LipAPI.mouth_carousel.move(target_container=LipAPI.preview_area)

                prev_hide.set_value(False)

                if container == 'left':
                    LipAPI.preview_area = card_left_preview
                    run_it()
                elif container == 'top':
                    LipAPI.preview_area = card_top_preview
                    run_it()
                elif container == 'right':
                    LipAPI.preview_area = card_right_preview
                    run_it()

            prev_exp = ui.expansion('Preview').classes('bg-cyan-500')
            with prev_exp:
                """
                def tab_preview():
                    my.disable()
                    ui.navigate.to('/preview', new_tab=True)
                """

                def show_preview(prev):
                    card_left_preview.set_visibility(False)
                    card_top_preview.set_visibility(False)
                    card_right_preview.set_visibility(False)
                    if prev is True:
                        LipAPI.preview_area.set_visibility(True)
                    else:
                        LipAPI.preview_area.set_visibility(False)

                with ui.row().classes('self-center'):
                    ui.label('Position').classes('self-center')
                    # ui.icon('open_in_new').on('click',lambda:tab_preview())
                ui.toggle(['left', 'top', 'right'], value='right', on_change=lambda v: move_preview(v.value))
                with ui.row().classes('self-center'):
                    ui.button(icon='add', on_click=lambda: LipAPI.mouth_carousel.next()).props('round dense')
                    ui.button(icon='remove', on_click=lambda: LipAPI.mouth_carousel.previous()).props('round dense')
                prev_hide = ui.switch('Show', on_change=lambda v: show_preview(v.value), value=True)
                prev_hide.classes('self-center')
                prev_hide.set_value(False)

        with ui.card().tight().classes('bg-cyan-400'):
            ui.label(' ')
            wvs_exp = ui.expansion('WledVideoSync').classes('bg-cyan-500')
            with wvs_exp:
                with ui.column():
                    wvs_ip = ui.input('Server IP', value='127.0.0.1')
                    with ui.row():
                        wvs_port = ui.number('Port', value=8000)
                        wvs_path = ui.input('Path (opt)', value='/ws')
                        wvs_activate = ui.checkbox('activate', on_change=manage_wvs_client)
                        wvs_send_metadata = ui.checkbox('Metadata')

            ui.label(' ')
            ui.separator()

            osc_exp = ui.expansion('OSC').classes('bg-cyan-500')
            with osc_exp:
                with ui.column():
                    osc_address = ui.input('Address', value='/WLEDLipSync')
                    osc_ip = ui.input('Server IP', value='127.0.0.1')
                    with ui.row():
                        osc_port = ui.number('Port', value=12000)
                        osc_activate = ui.checkbox('activate', on_change=manage_osc_client)
                        osc_send_metadata = ui.checkbox('Metadata')

            ui.separator()

            send_seek = ui.checkbox('Send when Seek', value=True)

    if LipAPI.source_file != '':
        audio_input.value = LipAPI.source_file
        await set_file_name()
        # await load_mouth_cue()

    if LipAPI.net_status_timer is not None:
        LipAPI.osc_client = None
        LipAPI.wvs_client = None
        net_row.update()
        LipAPI.net_status_timer.active = False

    await wavesurfer()


@ui.page('/edit')
async def edit_cue_buffer():
    utils.apply_custom()
    await edit_mouth_time_buffer()


@ui.page('/preview')
async def preview_page():
    utils.apply_custom()
    with ui.card(align_items='center').classes('w-full'):
        await create_mouth_model()


@ui.page('/audiomass')
async def audio_editor():
    utils.apply_custom()
    audiomass_file = LipAPI.file_to_analyse.replace('.wav', '.mp3')
    audiomass_file = audiomass_file.replace('./', '/')
    ui.navigate.to(f'/audiomass/src/index.html?WLEDLipSyncFilePath={audiomass_file}')

"""
app specific param
"""

app.add_media_files('/media', 'media')
app.add_static_files('/assets', 'assets')
app.add_static_files('/output', 'output')
app.add_static_files('/audiomass', 'audiomass')

"""
run niceGUI
reconnect_timeout: need big value if load thumbs
"""
ui.run(native=False, reload=False, reconnect_timeout=30)
