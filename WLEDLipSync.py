# Compilation mode, standalone everywhere, except on macOS there app bundle
# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --include-raw-dir=rhubarb/mac=rhubarb/mac
# nuitka-project-if: {OS} == "Windows":
#    nuitka-project: --onefile-windows-splash-screen-image={MAIN_DIRECTORY}/splash-screen.png
#    nuitka-project: --include-raw-dir=rhubarb/win=rhubarb/win
# nuitka-project-if: {OS} == "Linux":
#    nuitka-project: --include-raw-dir=rhubarb/linux=rhubarb/linux
#    nuitka-project: --include-module=gi
#    nuitka-project: --include-module=qtpy
# nuitka-project-if: os.getenv("DEBUG_COMPILATION", "no") == "yes":
#    nuitka-project: --force-stdout-spec=WLEDLipSync.out.txt
#    nuitka-project: --force-stderr-spec=WLEDLipSync.err.txt
# nuitka-project: --mode=onefile
# nuitka-project: --nofollow-import-to=doctest
# nuitka-project: --noinclude-default-mode=error
# nuitka-project: --include-raw-dir=tmp=tmp
# nuitka-project: --include-raw-dir=log=log
# nuitka-project: --include-raw-dir=assets=assets
# nuitka-project: --include-raw-dir=config=config
# nuitka-project: --include-raw-dir=media=media
# nuitka-project: --include-raw-dir=audiomass=audiomass
# nuitka-project: --include-raw-dir=output=output
# nuitka-project: --include-raw-dir=chataigne=chataigne

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
             +  |_lyrics.txt  <--- optional text file with the dialog text to get more reliable results

For mouths model/images, need 9 images representing mouth positions:
./media/image/model/<model name>
                    |_A.png ... X.png

see: https://github.com/DanielSWolf/rhubarb-lip-sync

Send mouth cues to OSC and WS ...
Depend on how many mouth cues defined and if short interval, in some rare case, could miss letter during audio playback
    --> timeupdate frequency depend on several external factor , see HTML5 audio element doc
This is one of reason why actual letter and future one are sent on same message record.
On second, a mouth loop will occur during play time and executed every 10ms.

09/10/2024 : there is a problem playing  file when refresh the browser : need investigation
"""
import json
import time
import cv2
import os
import sys
import asyncio
import tkinter as tk
from tkinter import PhotoImage

import utils
import logging
import concurrent_log_handler
import taglib
import niceutils
import chataigne

from str2bool import str2bool
from OSCClient import OSCClient
from WSClient import WebSocketClient
from pathlib import Path
from PIL import Image
from nicegui import ui, app, native, run
from rhubarb import RhubarbWrapper
from niceutils import LocalFilePicker
from typing import List, Union
from math import trunc
from ytmusic import MusicInfoRetriever
from niceutils import AnimatedElement as Animate

if sys.platform.lower() == 'win32':
    from asyncio import WindowsSelectorEventLoopPolicy, set_event_loop_policy

    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

# rhubarb
rub = RhubarbWrapper()
# music info
ret = MusicInfoRetriever()
# chataigne
cha = chataigne.ChataigneWrapper()

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

    # animate or not
    do_animation = str2bool(custom_config['animate-ui'])

else:

    def on_ok_click():
        # Close the window when OK button is clicked
        root.destroy()


    # Create the main window
    root = tk.Tk()
    root.title("WLEDLipSync Portable Extraction")
    root.configure(bg='#0E7490')  # Set the background color

    abs_pth = os.path.abspath(sys.argv[0])
    work_dir = os.path.dirname(abs_pth).replace('\\', '/')

    # Change the window icon
    icon = PhotoImage(file=f'{work_dir}/WLEDLipSync/favicon.png')
    root.iconphoto(False, icon)

    config_file = work_dir + "/WLEDLipSync/config/WLEDLipSync.ini"

    # Define the window's contents
    info_text = ("Extracted executable to WLEDLipSync folder.....\n\n \
    You can safely delete this file after extraction finished to save some space.\n \
    (the same for WLEDLipSync.out.txt and err.txt if there ...)\n\n \
    Go to WLEDLipSync folder and run WLEDLipSync-{OS} file\n \
    This is a portable version, nothing installed on your system and can be moved where wanted.\n\n \
    Enjoy using WLEDLipSync\n\n \
    -------------------------------------------------------------------------------------------------\n \
    THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,\n \
    INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n \
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.\n \
    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,\n \
    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n \
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\n \
    -------------------------------------------------------------------------------------------------\n ")

    info_label = tk.Label(root, text=info_text, bg='#0E7490', fg='white', justify=tk.LEFT)
    info_label.pack(padx=10, pady=10)

    # Create the OK button
    ok_button = tk.Button(root, text="Ok", command=on_ok_click, bg='gray', fg='white')
    ok_button.pack(pady=10)

    # Start the Tkinter event loop
    root.mainloop()

    sys.exit()


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
        status_timer: Timer for network status.
        osc_client: OSC client for communication.
        wvs_client: WVS client for communication.
        data_changed (bool): Indicates if data has been changed by the user.
        preview_area: Area for displaying the model.

        mouth_to_image (dict): Mapping of mouth shapes to image indices.
    """

    player_status = ''
    player_time: float = 0
    scroll_graphic: bool = True
    mouth_times_buffer = {}  # buffer dict contains result from rhubarb
    mouth_times_selected = []  # list contain time selected
    mouth_images_buffer: List = []  # list contains mouth images from a model
    mouths_buffer_thumb: List = []  # contains thumb mouth images
    thumbnail_width: int = 64  # thumb image width
    mouth_carousel = None  # carousel object
    mouth_area_h: Union[ui.scroll_area, None] = None  # scroll area object
    audio_duration: Union[float, None] = None  # audio file duration
    source_file = ''
    output_file = ''
    file_to_analyse = ''
    lyrics_file = ''
    wave_show = True
    mouth_cue_show = True
    status_timer = None
    osc_client = None
    wvs_client = None
    cha_client = None
    data_changed = False  # True if some data has been changed by end user
    preview_area = None  # area where to display model

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


async def create_mouth_model(mouth_folder: str = './media/image/model/default'):
    """
    Loads mouth images from a specified folder into the LipAPI buffer.

    This function scans the given folder for image files, loads them asynchronously,
    and stores them in the LipAPI mouth image buffers. It also checks if enough images
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
        utils.load_image_async(str(img_path))
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
    LipAPI.mouth_carousel.classes('self-center')
    with LipAPI.mouth_carousel:
        for i in range(image_number):
            await create_carousel_slide(i)
            await create_thumbnail(i)

    # put to default image
    LipAPI.mouth_carousel.set_value(str(get_index_from_letter('X')))


async def create_carousel_slide(index: int):
    """Creates a carousel slide for displaying a mouth image.

    This function generates a slide in the carousel UI that displays a mouth image
    from the LipAPI mouth_images_buffer at the specified index. It also includes
    an interactive button that shows the image dimensions and serves as a tooltip.

    Args:
        index (int): The index of the mouth image in the LipAPI mouth_images_buffer.

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
        index (int): The index of the mouth image in the LipAPI mouth_images_buffer.

    Returns:
        None
    """

    image = LipAPI.mouth_images_buffer[index]
    height, width, _ = image.shape
    aspect_ratio = height / width
    new_height = int(LipAPI.thumbnail_width * aspect_ratio)
    resized_image = cv2.resize(image, (LipAPI.thumbnail_width, new_height))
    LipAPI.mouths_buffer_thumb.append(resized_image)


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
    from the LipAPI mouth_to_image mapping. If the letter is not found,
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
    from the LipAPI mouth_to_image mapping. If the index does not correspond
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
        try:
            with open(LipAPI.output_file, 'w', encoding='utf-8') as file:
                json.dump(LipAPI.mouth_times_buffer, file, ensure_ascii=False, indent=4)
                LipAPI.data_changed = False
            ui.notify('Data saved successfully.')
        except Exception as e:
            ui.notify(f'Failed to save data: {e}')
            logger.error(f'Failed to save data: {e}')
        dialog.close()

    if LipAPI.output_file and (LipAPI.data_changed or force):
        with ui.dialog() as dialog, ui.card():
            dialog.open()
            with ui.row():
                ui.button('Save changes to file', on_click=run_it)
                ui.button('Exit without saving', on_click=dialog.close)
    else:
        ui.notify('Nothing to save.')


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


async def set_audio_duration():
    """
    Updates the audio duration for the vocal player.

    This function loads the audio element for the vocal player and retrieves
    its current duration, storing it in the LipAPI audio_duration attribute.

    Returns:
        None
    """

    LipAPI.audio_duration = await niceutils.get_audio_duration('player_vocals')


def add_all_markers():
    """ run java to add all markers """

    ui.run_javascript(f'LoadMouthCues("{LipAPI.output_file}");', timeout=5)


async def mouth_cue_action(osc_address):
    LipAPI.player_time = await niceutils.get_player_time()
    await run.io_bound(loop_mouth_cue, osc_address)


def loop_mouth_cue(osc_address):
    def to_do():
        actual_cue_record, next_cue_record = utils.find_cue_point(LipAPI.player_time, LipAPI.mouth_times_buffer)
        start = str(actual_cue_record['start'])
        value = actual_cue_record['value']
        cue_to_test = start + value
        player_2digit = trunc(LipAPI.player_time * 100) / 100

        if cue_to_test not in triggered_values:
            # set the index image in carousel (letter)
            if LipAPI.mouth_carousel is not None:
                LipAPI.mouth_carousel.set_value(str(get_index_from_letter(actual_cue_record['value'])))
            # send osc message
            if LipAPI.osc_client is not None:
                LipAPI.osc_client.send_message(
                    f'{osc_address}/mouthCue/',
                    [
                        "{:.3f}".format(LipAPI.player_time),
                        actual_cue_record['value'],
                        next_cue_record['start'],
                        next_cue_record['end'],
                        value,
                    ],
                )
            # send wvs message
            if LipAPI.wvs_client is not None:
                ws_msg = {"action": {"type": "cast_image",
                                     "param": {"image_number": get_index_from_letter(actual_cue_record['value']),
                                               "device_number": 0,
                                               "class_name": "Media",
                                               "fps_number": 50,
                                               "duration_number": 1}}}

                LipAPI.wvs_client.send_message(ws_msg)
            logger.info(
                f"{str(player_2digit)} {str(value)} {str(round(time.time() * 1000))}"
            )
            if str2bool(app_config['send_only_once']):
                triggered_values.add(cue_to_test)

        time.sleep(0.01)
        LipAPI.player_time += 0.01

    triggered_values = set()  # Track triggered values
    while LipAPI.player_status == 'play':
        to_do()

    if LipAPI.player_status == 'end' and str2bool(app_config['send_end']):
        to_do()


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

    audiomass_file = LipAPI.file_to_analyse.replace('.wav', '.mp3')
    audiomass_file = audiomass_file.replace('./', '/')
    # http://yourdomain.com/index.html?yourParam=exampleValue

    audio_dialog = ui.dialog() \
        .props(add='full-width full-height transition-show="slide-up" transition-hide="slide-down"')

    with audio_dialog:
        audio_dialog.open()
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
                    new_editor = ui.button(icon='edit', color='yellow')
                    new_editor.on('click', lambda: ui.navigate.to('/audiomass', new_tab=True))
                    new_editor.props(add='round outline size="8px"')
                    new_editor.tooltip('Open editor in new tab')
                    close = ui.button(icon='close', color='red')
                    close.on('click', lambda: audio_dialog.close())
                    close.props(add='round outline size="8px"')
                    close.tooltip('Close editor')


async def modify_letter(start_time, letter_lbl):
    """ create letter modification dialog and update """

    def upd_letter(new_letter):
        """ update label and buffer """
        for i_cue in LipAPI.mouth_times_buffer['mouthCues']:
            if i_cue['start'] == start_time:
                i_cue['value'] = new_letter
                letter_lbl.style(add='color:orange')
                LipAPI.data_changed = True
                logger.debug(f'new letter set {new_letter}')
                break

        letter_lbl.text = new_letter
        dialog_l.close()

    with ui.dialog() as dialog_l, ui.card():
        """ dialog for letter update """

        dialog_l.open()
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

    def run_chataigne(action):
        """
        Run or Stop chataigne

        """
        if action == 'run':
            noisette = str(Path('chataigne/WLEDLipSync.noisette').resolve())
            cha.run(headless=False, file_name=noisette)
            logger.info('start chataigne')

        elif action == 'stop':
            cha.stop_process()
            cha_status.props(remove='color=green')
            cha_status.props(add='color=black')
            logger.info('stop chataigne')

    async def check_status():
        """
        Checks the network status of OSC and WVS clients.
        Check chataigne status.

        This function verifies the connectivity of the OSC and WVS clients by checking
        the status of their respective network ports. It updates the UI elements to reflect
        the current connection status and stops the WVS client if it is not connected.

        Returns:
            None
        """

        logger.info('check status')

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

        if LipAPI.cha_client is not None:
            # check net status, TCP port
            result = await utils.check_ip_alive(ip_address=cha_ip.value, port=int(cha_port.value))
            if result is True:
                # set value depend on return code
                link_cha.props(remove="color=yellow")
                link_cha.props(add="color=green")
            else:
                link_cha.props(remove="color=green")
                link_cha.props(add="color=yellow")
                LipAPI.cha_client.stop()
                LipAPI.cha_client = None
                spleeter.disable()

        if cha.is_running():
            logger.info('chataigne running')
            cha_status.props(add='color=green')

        if not os.path.isdir(f'{utils.chataigne_data_folder()}/modules/SpleeterGUI-Chataigne-Module-main'):
            spleeter.disable()

        if wvs_activate.value is False and osc_activate.value is False and cha_activate is False:
            link_wvs.props(remove="color=green")
            link_wvs.props(remove="color=yellow")
            link_cha.props(remove="color=green")
            link_cha.props(remove="color=yellow")
            link_osc.props(remove="color=yellow")
            link_osc.props(remove="color=green")
            LipAPI.status_timer.active = False

    async def manage_status_timer():
        """
        Manage the status timer for the LipAPI.

        This asynchronous function creates a new status timer if one does not
        already exist, or activates the existing timer. The timer is set to check
        the status at regular intervals.

        Returns:
            None
        """
        # create or activate status  timer
        if LipAPI.status_timer is None:
            LipAPI.status_timer = ui.timer(5, check_status)
        else:
            LipAPI.status_timer.active = True

    async def manage_cha_client():
        """
        Manages the WebSocket client for cha activation and deactivation.

        This function activates the WVS client if the corresponding toggle is enabled,
        creating a new WebSocket connection if one does not already exist. It also sends
        an initialization message and manages the network status timer, stopping the client
        if the toggle is disabled.

        Returns:
            None
        """

        logger.debug('CHA activation')

        await manage_status_timer()

        if cha_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.cha_client is None:
                ws_address = "ws://" + str(cha_ip.value) + ":" + str(int(cha_port.value)) + str(cha_path.value)
                LipAPI.cha_client = WebSocketClient(ws_address)
                LipAPI.cha_client.run()
            await asyncio.sleep(2)
            # send init message
            cha_msg = {"action": {"type": "init_cha", "param": {"connection": "true", "WLEDLipSync": "true"}}}
            LipAPI.cha_client.send_message(cha_msg)
            spleeter.enable()

        else:
            # we stop the client
            if LipAPI.cha_client is not None:
                LipAPI.cha_client.stop()
            LipAPI.cha_client = None
            spleeter.disable()
            link_cha.props(remove="color=green")
            link_cha.props(remove="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.status_timer.active is True and osc_activate.value is False and wvs_activate.value is False:
                logger.debug('stop timer')
                LipAPI.status_timer.active = False

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

        await manage_status_timer()

        if wvs_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.wvs_client is None:
                ws_address = "ws://" + str(wvs_ip.value) + ":" + str(int(wvs_port.value)) + str(wvs_path.value)
                LipAPI.wvs_client = WebSocketClient(ws_address)
                LipAPI.wvs_client.run()
            await asyncio.sleep(2)
            # send init message
            wvs_msg = {"action": {"type": "init_wvs", "param": {"metadata": "", "mouthCues": ""}}}
            # add metadata if requested
            if wvs_send_metadata.value is True:
                wvs_msg = {"action": {"type": "init_wvs", "param": LipAPI.mouth_times_buffer}}
                wvs_send_metadata.value = False
            LipAPI.wvs_client.send_message(wvs_msg)

        else:
            # we stop the client
            if LipAPI.wvs_client is not None:
                LipAPI.wvs_client.stop()
            LipAPI.wvs_client = None
            link_wvs.props(remove="color=green")
            link_wvs.props(remove="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.status_timer.active is True and osc_activate.value is False and cha_activate.value is False:
                logger.debug('stop timer')
                LipAPI.status_timer.active = False

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

        await manage_status_timer()

        if osc_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.osc_client is None:
                LipAPI.osc_client = OSCClient(str(osc_ip.value), int(osc_port.value))
            # send init message
            osc_msg = {"action": {"type": "init_osc", "param": {}}}
            if osc_send_metadata.value is True:
                osc_msg = {"action": {"type": "init_osc", "param": LipAPI.mouth_times_buffer}}
                osc_send_metadata.value = False
            LipAPI.osc_client.send_message(osc_address.value, osc_msg)

        else:
            # we stop the client
            if LipAPI.osc_client is not None:
                LipAPI.osc_client.stop()
            LipAPI.osc_client = None
            link_osc.props(remove="color=green")
            link_osc.props(remove="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.status_timer.active is True and wvs_activate.value is False and cha_activate.value is False:
                logger.debug('stop timer')
                LipAPI.status_timer.active = False

    async def validate_file(file_name):
        """ file input validation """

        # check some requirements
        if file_name == '':
            ui.notify('Blank value not allowed', type='negative')
            logger.error('Blank value not allowed')
            return False
        elif not file_name.lower().endswith('.mp3'):
            ui.notify('Only MP3', type='negative')
            logger.error('Only MP3')
            return False
        elif not os.path.isfile(file_name):
            ui.notify(f'File {file_name} does not exist', type='negative')
            logger.error(f'File {file_name} does not exist')
            return False

        return True

    async def check_audio_input(file_name):
        """ check input and retrieve info from ytmusicapi """

        if await validate_file(file_name):
            await run.io_bound(song_info, file_name)

    async def approve_set_file_name():
        """ dialog to approve load new audio file """

        async def run_it():
            if LipAPI.data_changed is True:
                ui.notification('Changed data has been detected, you need to save before or refresh to bypass',
                                position='center', type='info', timeout=10, close_button=True)
            else:
                dialog.close()
                # disable button
                load_mouth_button.disable()
                edit_mouth_buffer.disable()
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
        #  set some init value
        player_vocals.seek(0)
        player_accompaniment.seek(0)
        spinner_accompaniment.set_visibility(False)
        spinner_vocals.set_visibility(False)
        stems.set_visibility(False)
        analyse_file.set_visibility(False)
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
        if await validate_file(file_path):
            # extract file name only
            file_name = os.path.basename(file_path)
            file_info = os.path.splitext(file_name)
            file = file_info[0]
            file_folder = app_config['audio_folder'] + file + '/'

            # check if folder / file  not exist (not stems)
            if not os.path.isfile(file_folder + 'vocals.mp3'):
                if not os.path.isdir(file_folder):
                    ui.notify(f'folder {file_folder} does not exist, creating ...', type='info')
                    os.mkdir(file_folder)
                # in this case, source file is supposed not been separated in stems
                ui.notify(f'Analysis done from audio source file {file_name}.')
                out = app_config['output_folder'] + file + '/' + 'rhubarb.json'
                if os.path.isfile(out):
                    ui.notify(f'Found an existing analysis file ...  {out}.')
                # convert mp3 to wav
                utils.convert_audio(file_path, file_folder + file + '.wav')
                player_vocals.set_source(file_path)
                audio_vocals.tooltip(file_path)
                audio_vocals.update()
                player_accompaniment.set_source('')
                audio_accompaniment.tooltip('TBD')
                audio_accompaniment.update()
                LipAPI.file_to_analyse = file_folder + file + '.wav'
                LipAPI.lyrics_file = file_folder + 'lyrics.txt'
                #
                ui.timer(1, set_audio_duration, once=True)

            else:
                #  vocals.mp3 exist so stems
                ui.notify('We will do analysis from stems files ...', position='top')
                stems.set_visibility(True)
                # specific case for vocals
                # always (re)generate wav from mp3, rhubarb will need it
                utils.convert_audio(file_folder + 'vocals.mp3', file_folder + 'vocals.wav')
                ui.notify('auto generate wav file')
                # double check (e.g. no more disk space)
                if not os.path.isfile(file_folder + 'vocals.wav'):
                    ui.notification('ERROR on wav file creation', position='center', type='negative')
                    player_vocals.set_source('')
                    LipAPI.audio_duration = None
                    return
                # set players
                player_vocals.set_source(file_folder + 'vocals.mp3')
                audio_vocals.tooltip(file_folder + 'vocals.mp3')
                # this one is optional
                if os.path.isfile(file_folder + 'accompaniment.mp3'):
                    player_accompaniment.set_source(file_folder + 'accompaniment.mp3')
                    audio_accompaniment.tooltip(file_folder + 'accompaniment.mp3')
                else:
                    player_accompaniment.set_source('')
                    audio_accompaniment.tooltip(' ' * 20)
                    audio_accompaniment.update()
                #
                audio_vocals.update()
                audio_accompaniment.update()
                #
                LipAPI.file_to_analyse = file_folder + 'vocals.wav'
                LipAPI.lyrics_file = file_folder + 'lyrics.txt'

            # set params
            LipAPI.source_file = audio_input.value
            LipAPI.output_file = app_config['output_folder'] + file + '/' + 'rhubarb.json'
            if os.path.isfile(LipAPI.output_file):
                analyse_file.set_visibility(True)
            edit_mouth_buffer.enable()
            load_mouth_button.enable()
            run_icon.tooltip(f'Click here to analyse {LipAPI.file_to_analyse} with rhubarb')
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
            else:
                result = str(result[0])
            if len(result) > 0:
                result = './' + result
            if await validate_file(result):
                # disable button
                load_mouth_button.disable()
                edit_mouth_buffer.disable()
                audio_input.value = result
                await check_audio_input(result)

    async def run_analyse(dialog):
        """
        Initiates audio analysis based on the current state and user input.
        It checks for various conditions before starting the analysis and updates the UI accordingly.

        Args:
            dialog: The dialog interface used for user interaction.

        Returns:
            None

        Raises:
            None

        Examples:
            await run_analyse(my_dialog)
        """

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
            # rhubarb will append file extension
            analysis_output = LipAPI.output_file.replace('.json', '')
            rub.run(file_name=LipAPI.file_to_analyse, dialog_file=LipAPI.lyrics_file, output=analysis_output)

            # set some GUI
            spinner_analysis.set_visibility(True)
            player_vocals.pause()
            player_accompaniment.pause()
            spinner_accompaniment.set_visibility(False)
            spinner_vocals.set_visibility(False)
            load_model_button.disable()
            edit_mouth_buffer.disable()
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

    async def run_spleeter(dialog):
        """
        Initiates the Spleeter processing for the specified audio file.

        This function constructs a message to run Spleeter with the absolute path of the audio file and sends it to the
        Chataigne client. It also notifies the user of the initiation and checks if Spleeter is running,
        closing the dialog afterward.

        Args:
            dialog: The dialog to be closed once the Spleeter process is initiated.

        Returns:
            None

        Raises:
            None
        """
        # Get the absolute path of the current file
        audio_absolute_path = Path(audio_input.value).resolve()
        logger.debug(audio_absolute_path)
        # send action message
        cha_msg = {"action": {"type": "runSpleeter", "param": {"fileName": str(audio_absolute_path)}}}
        if LipAPI.cha_client is not None:
            LipAPI.cha_client.send_message(cha_msg)
            ui.notify('initiate Spleeter ....', type='warning')
            spleeter.props(add='loading')
        dialog.close()
        await run.io_bound(utils.check_spleeter_is_running, spleeter, audio_input.value, 2.0)

    async def split_audio():
        """
        Prompts the user to confirm the splitting of an audio file into stems using Spleeter.

        This function validates the specified audio file and opens a dialog to ask the user for confirmation
        before proceeding with the audio splitting process. It provides options to either confirm or cancel the action.

        Returns:
            None

        Raises:
            None
        """
        if await validate_file(audio_input.value):
            with ui.dialog() as dialog, ui.card():
                dialog.open()
                ui.label(f'Split file "{audio_input.value}" into stems with Spleeter')
                ui.label('Are You Sure ?')
                with ui.row():
                    ui.button('Yes', on_click=lambda: run_spleeter(dialog))
                    ui.button('No', on_click=dialog.close)

    async def analyse_audio():
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
        with ui.dialog() as dialog, ui.card():
            dialog.open()
            ui.label(f'Analyse file "{LipAPI.source_file}" with Rhubarb')
            ui.label(f'This will overwrite : {LipAPI.output_file}')
            ui.label('Are You Sure ?')
            with ui.row():
                ui.button('Yes', on_click=lambda: run_analyse(dialog))
                ui.button('No', on_click=dialog.close)

    def load_cues(dialog=None):
        """
        Loads mouth cues from a specified output file and updates the user interface accordingly.

        This function clears any existing mouth area, resets the mouth times buffer, and checks if a source file is set.
        If the output file exists, it reads the data and populates the mouth times buffer, notifying the user of the process.

        Args:
            dialog: An optional dialog to be closed before loading cues.

        Returns:
            None

        Raises:
            None
        """
        if dialog is not None:
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
            ui.notification('this could take some time .....', position='center', type='warning', spinner=True)

            if os.path.isfile(LipAPI.output_file):
                with open(LipAPI.output_file, 'r') as data:
                    LipAPI.mouth_times_buffer = json.loads(data.read())

                ui.timer(1, generate_mouth_cue, once=True)
                output_label.classes(remove='animate-pulse')
                output_label.style(remove='color: red')

            else:
                ui.notify('No analysis file to read')
                output_label.classes(add='animate-pulse')
                output_label.style(add='color: red')
        else:
            ui.notify('Source file blank ... load a new file')

    async def load_mouth_cue():
        """
        Prompts the user to confirm loading mouth cues if there are unsaved changes.

        This function checks if the data has changed and, if so, opens a dialog to ask the user for confirmation
        before loading the mouth cues. If there are no changes, it directly loads the cues without prompting.

        Returns:
            None

        Raises:
            None
        """
        if LipAPI.data_changed is True:
            with ui.dialog() as dialog, ui.card():
                dialog.open()
                ui.label(f'Detected changed data ...')
                ui.label('Are You Sure ?')
                with ui.row():
                    ui.button('Yes', on_click=lambda: load_cues(dialog))
                    ui.button('No', on_click=dialog.close)
        else:
            load_cues()

    async def load_mouth_model():
        """
        Loads a mouth model from a specified directory and updates the user interface accordingly.

        This function allows the user to select a directory containing mouth images, and if valid, it deletes any existing
        mouth carousel and generates a new one based on the selected images. It also updates the preview area with the
        first image from the loaded model.

        Returns:
            None

        Raises:
            None
        """
        result = await LocalFilePicker('./media/image/model', multiple=False)

        ui.notify(f'Selected :  {result}')

        if result is not None:
            if os.path.isdir(result[0]):
                if sys.platform.lower() == 'win32' and len(result) > 0:
                    result = str(result[0]).replace('\\', '/')
                else:
                    result = str(result[0])
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
                    # refresh central time image
                    img = Image.fromarray(LipAPI.mouths_buffer_thumb[0])
                    model_thumb.set_source(img)
                    model_thumb.update()

            else:
                logger.debug('you need to select folder')

    async def generate_mouth_cue():
        """
        Generates and displays mouth cues based on the current audio playback.

        This function sets up the user interface for displaying mouth cues, allowing users to interact with the cues
        by clicking on them to play audio or modify the associated letters. It manages the playback of audio segments
        and updates the visual representation of the cues in the UI.

        Returns:
            None

        Raises:
            None
        """

        async def select_letter(start_time: float, letter_lbl: ui.label):
            """
            Selects a letter associated with a specific start time and updates the label.

            This function logs the start time and the label, then calls another function to modify the letter based on the
            provided start time. It is intended to facilitate user interaction with the audio cues in the application.

            Args:
                start_time (float): The time in seconds associated with the letter selection.
                letter_lbl (ui.label): The label UI component that displays the selected letter.

            Returns:
                None

            Raises:
                None
            """
            logger.debug(str(start_time) + " " + str(letter_lbl))
            await modify_letter(start_time, letter_lbl)

        def position_player(seek_time: float, card: ui.card, rem: ui.icon, marker: str = 'X'):
            """
            Seeks the audio players to a specified time and updates the user interface accordingly.

            This function adjusts the playback position of both the vocal and accompaniment audio players to the given
            seek time. It also updates the visual representation of the associated UI card and creates a marker at the
            specified time, ensuring that the user interface reflects the current playback state.

            Args:
                seek_time (float): The time in seconds to seek the audio players.
                card (ui.card): The UI card to be updated with the new state.
                rem (ui.icon): The icon to be made visible after seeking.
                marker (str): The marker to be created at the specified time (default is 'X').

            Returns:
                None

            Raises:
                None
            """
            player_vocals.seek(seek_time)
            player_accompaniment.seek(seek_time)
            if seek_time not in LipAPI.mouth_times_selected:
                LipAPI.mouth_times_selected.append(seek_time)
                LipAPI.mouth_times_selected.sort()
            niceutils.create_marker(seek_time, marker)
            card.classes(remove='bg-cyan-700')
            card.classes(add='bg-red-400')
            rem.set_visibility(True)
            card.update()

        async def play_until(start_time: float):
            """
            Play audio from a specified start time until the next cue or the end of the audio.

            This function seeks to the given start time in the audio player and plays the audio until it reaches
            the next cue time or the end of the audio duration.
            It pauses the player once the playback duration is complete.

            Args:
                start_time (float): The time in seconds to start playback from.

            Returns:
                None

            Raises:
                None

            Examples:
                await play_until(10.5)
            """

            player_vocals.seek(start_time)
            end_cue = next((i_cue for i_cue in LipAPI.mouth_times_selected if i_cue > start_time),
                           LipAPI.audio_duration)
            duration = end_cue - start_time
            end_time = time.time() + duration
            player_vocals.play()

            while time.time() <= end_time:
                await asyncio.sleep(0.001)

            player_vocals.pause()
            logger.debug('End of play_until loop.')

        def set_default(seek_time: float, card: ui.card, rem: ui.icon):
            """
            Resets the visual state of a UI card and removes the specified seek time from the selected mouth times.

            This function updates the UI by changing the card's background color and hiding the associated icon.
            It also removes the specified seek time from the list of selected mouth times, ensuring that the UI reflects
            the current state of the playback.

            Args:
                seek_time (float): The time in seconds to be removed from the selected mouth times.
                card (ui.card): The UI card to be updated with the default state.
                rem (ui.icon): The icon to be hidden after resetting the state.

            Returns:
                None

            Raises:
                None
            """
            LipAPI.mouth_times_selected.remove(seek_time)
            card.classes(remove='bg-red-400')
            card.classes(add='bg-cyan-700')
            rem.set_visibility(False)
            logger.debug(LipAPI.mouth_times_selected)

        # Scroll area with timeline/images
        if do_animation:
            scroll_area_anim = Animate(ui.scroll_area, animation_name_in='flipInX', duration=2)
            LipAPI.mouth_area_h = scroll_area_anim.create_element()
        else:
            LipAPI.mouth_area_h = ui.scroll_area()
        LipAPI.mouth_area_h.classes('bg-cyan-700 w-400 h-40')
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
                                           lambda st=start, card=time_card, rem=ic_remove, lb=letter: position_player(
                                               st, card,
                                               rem, lb))
                            start_label.tooltip('Click to set player time')
                            start_label.style('cursor:grab')

                            ic_play = ui.icon('play_circle', size='xs').style(add='cursor: pointer')
                            ic_play.on('click', lambda st=start: play_until(st))

                        letter_label = ui.label(letter).style('cursor:pointer')
                        letter_label.on('click', lambda st=start, lb=letter_label: select_letter(st, lb))

        # Move to the required container
        LipAPI.mouth_area_h.move(target_container=card_mouth)

        # This could take some time
        ui.timer(1, niceutils.run_gencuedata, once=True)

        LipAPI.data_changed = False
        edit_mouth_buffer.enable()
        load_mouth_button.enable()

    async def player_time_action():
        """
        Set scroll area position
        Send WVS / OSC msg
        """

        LipAPI.player_time = await niceutils.get_player_time()

        actual_cue_record, next_cue_record = utils.find_cue_point(LipAPI.player_time, LipAPI.mouth_times_buffer)
        letter = next_cue_record['value']

        # if time zero hide spinner
        if LipAPI.player_time == 0:
            spinner_vocals.set_visibility(False)
        else:
            if LipAPI.player_status == 'play':
                spinner_vocals.set_visibility(True)

        # scroll central mouth cues
        if LipAPI.player_status == 'play' and LipAPI.scroll_graphic is True:
            if LipAPI.audio_duration is None:
                LipAPI.audio_duration = await niceutils.get_audio_duration('player_vocals')
            if LipAPI.mouth_area_h is not None:
                LipAPI.mouth_area_h.scroll_to(percent=((LipAPI.player_time * 100) / LipAPI.audio_duration) / 100,
                                              axis='horizontal')

        # set new value to central label
        new_label = (str(LipAPI.player_time) + ' | ' +
                     str(actual_cue_record['value']) +
                     ' | ' +
                     str(letter) +
                     ' - ' +
                     str(get_index_from_letter(letter)))
        time_label.set_text(new_label)

        if LipAPI.player_status != 'play' and LipAPI.mouth_carousel is not None:
            LipAPI.mouth_carousel.set_value(str(get_index_from_letter(actual_cue_record['value'])))

        # send osc message on seek
        if osc_activate.value is True and LipAPI.player_status != 'play' and send_seek.value is True:
            LipAPI.osc_client.send_message(osc_address.value + '/mouthCue/',
                                           ["{:.3f}".format(LipAPI.player_time),
                                            actual_cue_record['value'],
                                            next_cue_record['start'],
                                            next_cue_record['end'], letter])

        # send wvs message on seek
        if wvs_activate.value is True and LipAPI.player_status != 'play' and send_seek.value is True:
            ws_msg = {"action": {"type": "cast_image",
                                 "param": {"image_number": get_index_from_letter(actual_cue_record['value']),
                                           "device_number": 0,
                                           "class_name": "Media",
                                           "fps_number": 50,
                                           "duration_number": 1}}}

            LipAPI.wvs_client.send_message(ws_msg)

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
            new_value = int(round(data['value'] * 100))
            circular.set_value(new_value)
            if new_value == 100:
                spinner_analysis.set_visibility(False)
                load_model_button.enable()
                edit_mouth_buffer.enable()
                load_mouth_button.enable()
                ok_button.enable()
                logger.debug('Analysis Finished')

    async def sync_player(action):
        """
        Synchronizes the playback of vocal and accompaniment audio players based on the specified action.
        This asynchronous function can play, pause,
        or synchronize the accompaniment player to the current playback time of the vocal player.

        Args:
            action (str): The action to perform, which can be 'play', 'pause', or 'sync'.

        Returns:
            None

        """
        if action == 'play':
            player_vocals.play()
            player_accompaniment.play()
        elif action == 'pause':
            player_vocals.pause()
            player_accompaniment.pause()
        elif action == 'sync':
            play_time = await niceutils.get_player_time()
            player_accompaniment.seek(play_time)

    async def event_player_vocals(event):
        """
        Handles events related to the vocal audio player, updating the player status and UI accordingly.
        This asynchronous function responds to different events such as 'end', 'play', and 'pause',
        adjusting the visibility of a spinner and invoking a mouth cue action based on the current event.

        Args:
            event (str): The event to handle, which can be 'end', 'play', or 'pause'.

        Returns:
            None

        """
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

        await mouth_cue_action(osc_address.value)

    def event_player_accompaniment(event):
        """
        Handles events related to the accompaniment audio player, updating the UI spinner visibility based on the event.
        This function responds to 'end', 'pause', and 'play' events, showing or hiding the spinner accordingly.

        Args:
            event (str): The event to handle, which can be 'end', 'pause', or 'play'.

        Returns:
            None

        """
        if event == 'end' or event == 'pause':
            spinner_accompaniment.set_visibility(False)

        elif event == 'play':
            spinner_accompaniment.set_visibility(True)

    def show_song_tags():
        """
        Displays a dialog for viewing and editing song tags in JSON format.
        This function opens a dialog containing a JSON editor pre-filled with the current tags,
        allowing users to view the tags and close the dialog when finished.

        Returns:
            None

        """

        with ui.dialog() as tags_dialog, ui.card():
            tags_dialog.open()
            ui.json_editor({'content': {'json': tags_data.text}})
            ui.button('close', on_click=tags_dialog.close)

    def save_lyrics():
        """
        Saves the lyrics from the input data to a specified text file.
        This function checks if the lyrics data is not empty, creates the necessary directory if it does not exist,
        and writes the lyrics to a file named 'lyrics.txt' in the appropriate folder.

        Returns:
            None
        """

        if lyrics_data.value:
            try:
                logger.info('save lyrics')
                # extract file name only
                file_name = os.path.basename(audio_input.value)
                file_info = os.path.splitext(file_name)
                file = file_info[0]
                file_folder = str(os.path.join(app_config['audio_folder'], file))
                # check if folder not exist
                if not os.path.isdir(file_folder):
                    ui.notify(f'folder {file_folder} does not exist, creating ...')
                    os.mkdir(file_folder)
                lyrics_file = os.path.join(file_folder, 'lyrics.txt')
                with open(f'{lyrics_file}', 'w', encoding='utf-8') as f:
                    f.write(lyrics_data.value)
                ui.notification(f'Saving lyrics to {lyrics_file} for helping analysis ...', position='center',
                                type='info')
            except Exception as e:
                ui.notify(f'Failed to save lyrics: {e}', position='center', type='negative')
                logger.error(f'Failed to save lyrics: {e}')
        else:
            ui.notification(f'Nothing to save ...', position='center', type='warning')

    def show_dialog():
        """
        Displays a dialog for viewing dialog text.
        This function allows users to see dialog in a text area.

        Returns:
            None

        """
        with (ui.dialog() as lyrics_dialog, ui.card(align_items='center').classes('w-full')):
            lyrics_dialog.open()
            try:
                with open(LipAPI.lyrics_file, 'r', encoding='UTF-8') as f:
                    text = f.read()
                    lyrics = ui.textarea('DIALOG', value=text)
                    lyrics.classes('w-full')
                    lyrics.props(add='autogrow bg-color=blue-grey-4')
                    lyrics.style(add='text-align:center;')
            except Exception as e:
                logger.error(f"Not able to open file : {e}")
            ui.button('close', on_click=lyrics_dialog.close)

    def show_song_lyrics():
        """
        Displays a dialog for viewing and saving song lyrics.
        This function allows users to edit the lyrics in a text area and provides an option
        to save the lyrics to a specified file, creating the necessary directory if it does not exist.

        Returns:
            None

        """
        with (ui.dialog() as lyrics_dialog, ui.card(align_items='center').classes('w-full')):
            lyrics_dialog.open()
            lyrics = ui.textarea('LYRICS', value=lyrics_data.value)
            lyrics.classes('w-full')
            lyrics.props(add='autogrow bg-color=blue-grey-4')
            lyrics.style(add='text-align:center;')
            with ui.row():
                ui.button('close', on_click=lyrics_dialog.close)
                sav_lyrics = ui.button('save', on_click=save_lyrics)
                sav_lyrics.tooltip('Save lyrics for analysis')

    def song_info(file_name):
        """
        Retrieves and displays information about a song from a given MP3 file
        and additional data from the YouTube Music API.
        This function reads the song's metadata, updates the UI with the song details,
        and fetches lyrics and related information, including the artist's top songs.

        Args:
            file_name (str): The path to the MP3 file from which to extract song information.

        Returns:
            None

        """
        # made spinner visible
        song_spinner.set_visibility(True)

        # read tag data of the mp3 file
        with taglib.File(file_name) as song:
            logger.info(song.tags)
            # set info from tags
            artist_tag = 'None'
            title_tag = 'None'
            album_tag = 'None'
            year_tag = 'None'
            if 'ARTIST' in song.tags:
                artist_tag = song.tags['ARTIST'][0]
            if 'TITLE' in song.tags:
                title_tag = song.tags['TITLE'][0]
            if 'ALBUM' in song.tags:
                album_tag = song.tags['ALBUM'][0]
            if 'DATE' in song.tags:
                year_tag = song.tags['DATE'][0]
            song_name.set_text('Title : ' + title_tag)
            song_year.set_text('Year : ' + year_tag)
            song_album.set_text('Album : ' + album_tag)
            song_artist.set_text('Artist : ' + artist_tag)
        tags_data.set_text(song.tags)

        #
        song_length.set_text('length : ')
        artist_desc.set_text('info : ')
        artist_img.set_source('')
        lyrics_data.set_value('')
        album_img.set_source('')
        song1_img.set_source('')
        song1_title.set_text('')
        song2_img.set_source('')
        song2_title.set_text('')
        song3_img.set_source('')
        song3_title.set_text('')
        song4_img.set_source('')
        song4_title.set_text('')
        song5_img.set_source('')
        song5_title.set_text('')
        # get info from ytmusicapi
        info_from_yt = ret.get_song_info_with_lyrics(title_tag, artist_tag)
        logger.info(info_from_yt)

        try:
            if info_from_yt is not None:
                # main info
                if 'lyrics' in info_from_yt:
                    lyrics_data.set_value(info_from_yt['lyrics']['lyrics'])
                if 'length' in info_from_yt:
                    song_length.set_text('length : ' + info_from_yt['length'])
                if 'thumbnails' in info_from_yt:
                    album_img.set_source(info_from_yt['thumbnails'][0]['url'])
                if 'artistInfo' in info_from_yt:
                    artist_img.set_source(info_from_yt['artistInfo']['thumbnails'][0]['url'])
                    artist_desc.set_text(info_from_yt['artistInfo']['description'])

                # get top 5
                try:
                    song1_img.set_source(info_from_yt['artistInfo']['top_5'][0]['thumbnails'][0]['url'])
                    song1_title.set_text(info_from_yt['artistInfo']['top_5'][0]['title'])
                    song2_img.set_source(info_from_yt['artistInfo']['top_5'][1]['thumbnails'][0]['url'])
                    song2_title.set_text(info_from_yt['artistInfo']['top_5'][1]['title'])
                    song3_img.set_source(info_from_yt['artistInfo']['top_5'][2]['thumbnails'][0]['url'])
                    song3_title.set_text(info_from_yt['artistInfo']['top_5'][2]['title'])
                    song4_img.set_source(info_from_yt['artistInfo']['top_5'][3]['thumbnails'][0]['url'])
                    song4_title.set_text(info_from_yt['artistInfo']['top_5'][3]['title'])
                    song5_img.set_source(info_from_yt['artistInfo']['top_5'][4]['thumbnails'][0]['url'])
                    song5_title.set_text(info_from_yt['artistInfo']['top_5'][4]['title'])

                except IndexError:
                    logger.info('Error to retrieve top5 from ytmusicapi')

            else:
                logger.info('nothing from ytmusicapi')

        except IndexError:
            logger.info('Error to retrieve info from ytmusicapi')
        except Exception as e:
            logger.info(f'Error to retrieve info from ytmusicapi {e}')

        # hide spinner when finished
        song_spinner.set_visibility(False)

    def move_preview(container):
        """
        Moves the preview area of the LipAPI to a specified container position.
        This function updates the preview area based on the provided container argument
        and triggers the movement of the mouth carousel to the new location.

        Args:
            container (str): The target position for the preview area, which can be 'left', 'top', or 'right'.

        Returns:
            None

        """
        prev_hide.set_value(False)

        if container == 'left':
            LipAPI.preview_area = card_left_preview
        elif container == 'top':
            LipAPI.preview_area = card_top_preview
        elif container == 'right':
            LipAPI.preview_area = card_right_preview

        LipAPI.mouth_carousel.move(target_container=LipAPI.preview_area)

    def show_preview(prev):
        """
        Controls the visibility of the preview area based on the provided flag.
        This function hides all preview cards and sets the visibility of the LipAPI preview area
        according to the boolean value of the `prev` argument.

        Args:
            prev (bool): A flag indicating whether to show the preview area (True) or hide it (False).

        Returns:
            None
        """
        card_left_preview.set_visibility(False)
        card_top_preview.set_visibility(False)
        card_right_preview.set_visibility(False)
        if prev is True:
            LipAPI.preview_area.set_visibility(True)
        else:
            LipAPI.preview_area.set_visibility(False)

    # -----------------------------------------------------------------------------------------------------------------#
    # reset default at init
    LipAPI.data_changed = False
    #
    # Rhubarb instance, callback will send back two values: data and is_stderr (for STDErr capture)
    #
    rub.callback = update_progress

    #
    # Main UI generation
    #
    niceutils.apply_custom()

    # Add Animate.css to the HTML head
    ui.add_head_html("""
    <link rel="stylesheet" href="./assets/css/animate.min.css"/>
    """)
    #
    #
    if do_animation:
        card_top_preview_anim = Animate(ui.card, animation_name_in='fadeInDown', duration=1)
        card_top_preview = card_top_preview_anim.create_element()
    else:
        card_top_preview = ui.card()
    card_top_preview.tight().classes('self-center no-shadow no-border w-full h-1/3')
    card_top_preview.set_visibility(False)

    with ui.row(wrap=False).classes('w-full'):

        if do_animation:
            card_left_preview_anim = Animate(ui.card, animation_name_in='fadeInLeft', duration=1)
            card_left_preview = card_left_preview_anim.create_element()
        else:
            card_left_preview = ui.card()
        card_left_preview.tight().classes('self-center no-shadow no-border w-1/3')
        card_left_preview.set_visibility(False)

        card_main = ui.card().tight().classes('w-full')
        card_main.set_visibility(True)
        with card_main:

            if do_animation:
                card_mouth_anim = Animate(ui.card, animation_name_in='fadeInDown', duration=3)
                card_mouth = card_mouth_anim.create_element()
            else:
                card_mouth = ui.card()
            card_mouth.classes('w-full')
            card_mouth.props('id="CardMouth"')
            with card_mouth:
                with ui.row():
                    ic_save = ui.icon('save')
                    ic_save.on('click', lambda: save_data())
                    output_label = ui.label('Output')
                    output_label.bind_text_from(LipAPI, 'output_file')
                    output_label.style(add='padding-top:10px')
                    ic_refresh = ui.icon('refresh')
                    ic_refresh.on('click', lambda: ui.navigate.to('/'))
                    edit_mouth_buffer = ui.chip('Edit mouth Cues',
                                                icon='edit',
                                                text_color='yellow',
                                                on_click=niceutils.mouth_time_buffer_edit)
                    edit_mouth_buffer.disable()
            with ui.row().classes('border'):
                add_markers = ui.chip('Add', icon='add', color='red', on_click=lambda: add_all_markers())
                add_markers.tooltip('Add all markers')
                add_markers.bind_visibility(LipAPI, 'wave_show')
                del_markers = ui.chip('Clear', icon='clear', color='red', on_click=lambda: niceutils.clear_markers())
                del_markers.tooltip('clear all markers')
                del_markers.bind_visibility(LipAPI, 'wave_show')
                ui.chip('Audio Editor', icon='edit', text_color='yellow', on_click=lambda: audio_edit())
                ui.label('').bind_text_from(LipAPI, 'file_to_analyse').style(add='margin:10px')

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

            file_label = ui.label('File Name')
            file_label.classes('self-center')
            file_label.bind_text_from(LipAPI, 'source_file')

            # time info
            if do_animation:
                row_time_anim = Animate(ui.row, animation_name_in='flipInY', duration=2)
                row_time = row_time_anim.create_element()
            else:
                row_time = ui.row()
            row_time.classes('self-center border')

            with row_time:
                ui.icon('watch', size='xs').classes('self-center')
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
                    model_thumb = ui.image(model_img).classes('w-6 self-center')
                else:
                    model_thumb = ui.image('./media/image/model/default/X.png').classes('w-6 self-center')

            # players
            if do_animation:
                card_player_anim = Animate(ui.card, animation_name_in='fadeIn', duration=2)
                card_player = card_player_anim.create_element()
            else:
                card_player = ui.card()
            card_player.classes('self-center border bg-cyan-800')

            with card_player:

                with ui.row().classes('self-center'):
                    with ui.column():
                        # player for vocals part, need mp3 file
                        player_vocals = ui.audio('').props('id=player_vocals')
                        player_vocals.props('preload=auto')
                        player_vocals.on('timeupdate', lambda: player_time_action())
                        player_vocals.on('play', lambda: event_player_vocals('play'))
                        player_vocals.on('pause', lambda: event_player_vocals('pause'))
                        player_vocals.on('ended', lambda: event_player_vocals('end'))
                        spinner_vocals = ui.spinner('audio', size='lg', color='green')
                        spinner_vocals.set_visibility(False)
                        audio_vocals = ui.label('VOCALS').classes('self-center').tooltip('TBD')
                        with ui.row():
                            folder_out_list = ui.icon('list', size='sm')
                            folder_out_list.tooltip('folder')
                            folder_out_list.on('click', lambda: LocalFilePicker(os.path.dirname(LipAPI.output_file)))
                            folder_out_list.style(add='cursor: pointer')
                            audio_dialog = ui.icon('lyrics', size='sm')
                            audio_dialog.tooltip('dialog')
                            audio_dialog.style(add='cursor: pointer')
                            audio_dialog.on('click', lambda: show_dialog())
                            audio_tags = ui.icon('tags', size='sm')
                            audio_tags.tooltip('mp3 tags')
                            audio_tags.style(add='cursor: pointer')
                            audio_tags.on('click', lambda: niceutils.show_tags(LipAPI.source_file))
                            stems = ui.icon('thumb_up_alt', size='sm')
                            stems.tooltip('vocals')
                            stems.set_visibility(False)
                            analyse_file = ui.icon('thumb_up_alt', size='sm')
                            analyse_file.tooltip('analyse')
                            analyse_file.set_visibility(False)

                    # card area center
                    control_area_v = ui.card(align_items='center').classes('w-45 h-85 border bg-cyan-900')
                    with control_area_v:
                        spinner_analysis = ui.spinner('dots', size='sm', color='red')
                        spinner_analysis.set_visibility(False)
                        with ui.row(wrap=False):
                            circular = ui.circular_progress(min=1, max=100)
                            run_icon = ui.icon('rocket', size='lg')
                            run_icon.style('cursor: pointer')
                            run_icon.tooltip(f'Click to analyse {LipAPI.file_to_analyse} with Rhubarb')
                            run_icon.on('click', lambda: analyse_audio())
                            scroll_time = ui.checkbox('')
                            scroll_time.tooltip('check to auto scroll graphic mouth cue')
                            scroll_time.bind_value(LipAPI, 'scroll_graphic')
                        with ui.row():
                            sp_1 = ui.button(on_click=lambda: sync_player('play'), icon='play_circle').props('outline')
                            sp_1.tooltip('Play players')
                            sp_2 = ui.button(on_click=lambda: sync_player('pause'), icon='pause_circle').props(
                                'outline')
                            sp_2.tooltip('Pause players')
                        sync_player_button = ui.button(on_click=lambda: sync_player('sync'), icon='sync')
                        sync_player_button.tooltip('Sync accompaniment with vocals')
                        sync_player_button.classes('w-10')
                        sync_player_button.props('outline')
                        with ui.column():
                            with ui.row().classes('self-center').style("margin:-10px;"):
                                ui.label('WVS')
                                ui.label('CHA')
                                ui.label('OSC')
                            with ui.row().classes('self-center'):
                                link_wvs = ui.icon('link', size='xs')
                                link_wvs.style(add="padding-right:10px")
                                link_cha = ui.icon('link', size='xs')
                                link_osc = ui.icon('link', size='xs')
                                link_osc.style(add="padding-left:10px")
                    # player 2
                    with ui.column():
                        # player for musical part, need mp3 file
                        player_accompaniment = ui.audio('').props('id=player_accompaniment')
                        spinner_accompaniment = ui.spinner('audio', size='lg', color='green')
                        player_accompaniment.on('play', lambda: event_player_accompaniment('play'))
                        player_accompaniment.on('pause', lambda: event_player_accompaniment('pause'))
                        player_accompaniment.on('ended', lambda: event_player_accompaniment('end'))
                        spinner_accompaniment.set_visibility(False)
                        audio_accompaniment = ui.label('ACCOMPANIMENT').classes('self-center').tooltip('TBD')

            ui.separator()

            with ui.row():

                folder = ui.icon('folder', size='md', color='yellow')
                folder.style(add='cursor: pointer')
                folder.style(add='margin:10px')
                # made necessary checks
                folder.on('click', lambda: pick_file_to_analyze())
                # Add an input field for the audio file name
                audio_input = ui.input(placeholder='Audio file to analyse', label='Audio File Name')
                audio_input.on('focusout', lambda: check_audio_input(audio_input.value))
                # Add a Spleeter button to create stems
                spleeter = ui.button('spleeter', on_click=split_audio)
                spleeter.style("margin:10px;")
                spleeter.disable()
                # Add an OK button to refresh the waveform and set all players and data
                ok_button = ui.button('OK', on_click=approve_set_file_name)
                ok_button.style("margin:10px;")
                ui.checkbox('Wave').bind_value(LipAPI, 'wave_show')
                ui.checkbox('MouthCue').bind_value(LipAPI, 'mouth_cue_show')
                info = ui.checkbox('Info', value=False)
            if do_animation:
                song_info_anim = Animate(ui.card, animation_name_in='fadeInUp', duration=1)
                song_info_card = song_info_anim.create_element()
            else:
                song_info_card = ui.card()
            with song_info_card.classes('self-center'):
                song_info_card.bind_visibility_from(info, 'value')
                song_info_card.classes('bg-blue-grey-4')
                song_spinner = ui.spinner(size='xl').classes('self-center')
                song_spinner.set_visibility(False)
                with ui.row():
                    with ui.column():
                        song_name = ui.label('Title : ')
                        song_album = ui.label('Album : ')
                        album_img = ui.image('').classes('w-20 border')
                    with ui.column():
                        song_length = ui.label('length : ')
                        song_year = ui.label('Year : ')
                        with ui.row():
                            song_lyrics = ui.icon('lyrics', size='sm')
                            song_lyrics.style(add='cursor: pointer')
                            song_lyrics.on('click', lambda: show_song_lyrics())
                            lyrics_data = ui.textarea(value='')
                            lyrics_data.set_visibility(False)
                        with ui.row():
                            song_tags = ui.icon('tag', size='sm')
                            song_tags.style(add='cursor: pointer')
                            song_tags.on('click', lambda: show_song_tags())
                            tags_data = ui.label('')
                            tags_data.set_visibility(False)
                    with ui.column():
                        with ui.row():
                            song_artist = ui.label('Artist : ')
                            artist_img = ui.image('').classes('w-80 border')
                        artist_desc = ui.label('info: ')
                        ui.label('Top 5 : ')
                        with ui.row():
                            ui.label('1')
                            with ui.column():
                                song1_img = ui.image('').classes('w-20 border')
                                song1_title = ui.label('')
                                song1_title.style('max-width:8em')
                            ui.label('2')
                            with ui.column():
                                song2_img = ui.image('').classes('w-20 border')
                                song2_title = ui.label('')
                                song2_title.style('max-width:8em')
                            ui.label('3')
                            with ui.column():
                                song3_img = ui.image('').classes('w-20 border')
                                song3_title = ui.label('')
                                song3_title.style('max-width:8em')
                            ui.label('4')
                            with ui.column():
                                song4_img = ui.image('').classes('w-20 border')
                                song4_title = ui.label('')
                                song4_title.style('max-width:8em')
                            ui.label('5')
                            with ui.column():
                                song5_img = ui.image('').classes('w-20 border')
                                song5_title = ui.label('')
                                song5_title.style('max-width:8em')

            ui.label(' ')

            with ui.row():
                load_mouth_button = ui.button('Load MouthCue', on_click=load_mouth_cue)
                load_mouth_button.disable()
                load_model_button = ui.button('Load a model', on_click=load_mouth_model)

        if do_animation:
            card_right_preview_anim = Animate(ui.card, animation_name_in='fadeInRight', duration=1)
            card_right_preview = card_right_preview_anim.create_element()
        else:
            card_right_preview = ui.card()
        card_right_preview.tight().classes('self-center no-shadow no-border w-1/3')
        with card_right_preview:
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
            ui.switch('Show', on_change=lambda v: card_main.set_visibility(v.value), value=True)
        with ui.row(wrap=False):
            def toggle_anim(v):
                globals()['do_animation'] = v

            ui.switch('Animate', on_change=lambda v: toggle_anim(v.value), value=do_animation).style('margin-top:-20px')

        with ui.card(align_items='center').tight().classes('bg-cyan-400'):
            prev_exp = ui.expansion('Preview').classes('bg-cyan-500')
            with prev_exp:
                with ui.row().classes('self-center'):
                    ui.label('Position').classes('self-center')
                    # ui.icon('open_in_new').on('click',lambda:tab_preview())
                ui.toggle(['left', 'top', 'right'], value='right', on_change=lambda v: move_preview(v.value))
                with ui.row().classes('self-center'):
                    ui.button(icon='add', on_click=lambda: LipAPI.mouth_carousel.next()).props('round dense')
                    ui.button(icon='remove', on_click=lambda: LipAPI.mouth_carousel.previous()).props('round dense')
                with ui.row().classes('self-center'):
                    prev_hide = ui.switch('Show', on_change=lambda v: show_preview(v.value), value=False)

        with ui.card().tight().classes('bg-cyan-400'):
            ui.label(' ')
            wvs_exp = ui.expansion('WLEDVideoSync').classes('bg-cyan-600')
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

            osc_exp = ui.expansion('OSC').classes('bg-cyan-600')
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

        with ui.card().tight().classes('bg-cyan-400'):
            ui.label(' ')
            cha_exp = ui.expansion('CHAtaigne').classes('bg-cyan-600')
            if os.path.isfile(utils.chataigne_exe_name()):
                with cha_exp:
                    with ui.column():
                        with ui.row():
                            ui.toggle(['run', 'stop'], value='stop', on_change=lambda e: run_chataigne(e.value))
                            cha_status = ui.icon('online_prediction', size='sm')
                        cha_ip = ui.input('Server IP', value='127.0.0.1')
                        with ui.row():
                            cha_port = ui.number('Port', value=8080,
                                                 on_change=lambda e: utils.chataigne_settings(e.value))
                            cha_path = ui.input('Path (opt)', value='')
                            cha_activate = ui.checkbox('activate', on_change=manage_cha_client)
            else:

                ui.label(' ')
                inst = ui.button('install', icon='settings', on_click=lambda e: utils.ask_install_chataigne(e))
                inst.classes('self-center')

            ui.label(' ')
            ui.separator()

        ui.label(' ')
        ui.separator()

        stop = ui.button('STOP APP', on_click=app.shutdown, color='red').classes('self-center')
        stop.tooltip('Shutdown server/application')

        ui.label(' ')
        ui.separator()

    if LipAPI.source_file != '':
        audio_input.value = LipAPI.source_file
        await set_file_name()

    if LipAPI.status_timer is not None:
        LipAPI.osc_client = None
        LipAPI.wvs_client = None
        LipAPI.cha_client = None
        LipAPI.status_timer.active = False

    await niceutils.wavesurfer()

    ui.button('test', on_click=lambda: utils.show_message('tt'))

@ui.page('/edit')
async def edit_cue_buffer():
    """
    Handles the editing of the cue buffer in the application.
    This asynchronous function applies custom settings and then invokes the function to edit the mouth time buffer.

    Returns:
        None

    """
    niceutils.apply_custom()
    await edit_mouth_time_buffer()


@ui.page('/preview')
async def preview_page():
    """
    Displays the preview model page of the application.
    This asynchronous function applies custom settings and creates a carousel within a centered card layout.

    Returns:
        None

    """
    niceutils.apply_custom()
    with ui.card(align_items='center').classes('w-full'):
        await create_carousel()


@ui.page('/audiomass')
async def audio_editor():
    """
    Navigates to the audio editor page of the application.
    This asynchronous function applies custom settings and constructs the file path for the audio file to be analyzed,
    then redirects the user to the Audiomass editor with the appropriate parameters.
    Need take mp3 version instead wav one.

    Returns:
        None

    """
    niceutils.apply_custom()
    audiomass_file = LipAPI.file_to_analyse.replace('.wav', '.mp3')
    audiomass_file = audiomass_file.replace('./', '/')
    ui.navigate.to(f'/audiomass/src/index.html?WLEDLipSyncFilePath={audiomass_file}')


async def startup_actions():
    logger.info('startup actions')
    utils.chataigne_settings()
    if not os.path.isfile(rub._exe_name):
        logger.info('rhubarb missing... proceed to installation')
        await utils.run_install_rhubarb()


def shutdown_actions():
    """
    Executes actions that are intended to be performed during the shutdown of the application.
    This function logger.infos a message indicating that shutdown actions are taking place and stops any ongoing processes.

    Returns:
        None
    """

    logger.info('shutdown actions')
    # stop Chataigne
    logger.info('stop chataigne')
    cha.stop_process()
    # remove python portable that has been downloaded during installation
    logger.info('clean tmp')
    if os.path.isfile('tmp/Pysp310.zip'):
        os.remove('tmp/Pysp310.zip')
    #
    message = "WLEDLipSync -- You can close the browser now."
    utils.inform_window(message)


"""
app specific param
"""

app.add_media_files('/media', 'media')
app.add_static_files('/output', 'output')
app.add_static_files('/audiomass', 'audiomass')
app.add_static_files('/assets', 'assets')
app.add_static_files('/config', 'config')

app.on_startup(startup_actions)
app.on_shutdown(shutdown_actions)

"""
run niceGUI
reconnect_timeout: need big value if load thumbs
"""
ui.run(native=False, reload=False, reconnect_timeout=3, port=8081)
