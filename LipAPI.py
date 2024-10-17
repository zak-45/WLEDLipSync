"""
a: zak-45
d: 09/10/2024
v: 1.0.0.0

Application to generate automatic Lip sync from a mp3 file.

File need to be split into two different audio files:
    1) vocals.mp3  (will be automatically converted to wav for Rhubarb)
    2) accompaniment.mp3 for music only
    This can be done by using SpleeterGUI: https://github.com/zak-45/SpleeterGUI-Chataigne-Module
    or any other tool able to split music into stems

Input files needs to be under ./media folder.
The structure is like that for song name : Mytest of all-time.mp3
./media/audio/Mytest of all-time
                |_vocals.mp3
                |_accompaniment.mp3

As output, this will generate a json file with corresponding time/mouth positions
./media/audio/Mytest of all-time
                |_WLEDLipSync.json
             +  |_vocals.wav <---- this one is used by rhubarb external program and created automatically if missing

For mouths model/images, need 9 images representing mouth positions:
./media/image/model/<model name>
                    |_A.png ... X.png

see: https://github.com/DanielSWolf/rhubarb-lip-sync


09/10/2024 : there is a problem playing  file when refresh the browser : need investigation
"""
import json

from PIL import Image
import cv2
import os
import sys

import utils

from nicegui import ui, app, run
from rhubarb import RhubarbWrapper
from niceutils import LocalFilePicker

if sys.platform.lower() == 'win32':
    from asyncio import WindowsSelectorEventLoopPolicy, set_event_loop_policy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())

class LipAPI:

    player_status = ''
    scroll_graphic : bool = True
    mouth_times_buffer = {}  # buffer dict contains result from rhubarb
    mouth_images_buffer = [] # list contains mouth images from a model
    thumbnail_width = 64  # thumb image width
    mouths_buffer_thumb = [] # contains thumb mouth images
    mouth_carousel = None  # carousel object
    mouth_area_h = None  # scroll area object
    source_file = ''
    output_file = ''
    file_to_analyse = ''
    wave_show = True
    mouth_cue_show = True
    audio_duration = None
    net_status_timer = None
    osc_client = None
    wvs_client = None

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


async def get_audio_duration(player):
    """
    Get audio duration
    :param player:
    :return: duration
    """
    duration = await ui.run_javascript(f'var audio=document.getElementById("{player}"); audio.duration;', timeout=2)
    return duration

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
    """Return the index associated with the given letter."""

    return LipAPI.mouth_to_image.get(letter, None)  # Returns None if letter is not found


async def create_mouth_model(folder: str = './media/image/model/anime'):
    """ Load a model into buffer """

    LipAPI.mouth_images_buffer = []
    if LipAPI.mouth_carousel is not None:
        LipAPI.mouth_carousel.clear()

    # Get all files in the folder and sort them by filename
    filenames = sorted(os.listdir(folder))

    # Define supported image extensions
    supported_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')

    # load images from folder using cv2
    for filename in filenames:
        if filename.lower().endswith(supported_extensions):
            img_path = os.path.join(folder, filename)
            if os.path.isfile(img_path):
                try:
                    img = cv2.imread(img_path, cv2.IMREAD_COLOR)  # Load image in color
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    if img is not None:
                        LipAPI.mouth_images_buffer.append(img)
                    else:
                        print(f"Could not open image {filename}: Image is None")
                except Exception as e:
                    print(f"Could not open image {filename}: {e}")

    # we need 9 images
    if len(LipAPI.mouth_images_buffer) < 9:
        print(f'ERROR not enough images loaded into buffer :{len(LipAPI.mouth_images_buffer)}')
    else:
        print(f'images loaded into buffer :{len(LipAPI.mouth_images_buffer)}')
        # create carousel for preview and
        # Generate thumbs from an array image
        # this will take mouths_buffer and populate mouths_buffer_thumb
        # Used to minimize time for page creation but consume more memory
        image_number = len(LipAPI.mouth_images_buffer)
        with ui.carousel(animated=True, arrows=True, navigation=True).props('height=480px') as LipAPI.mouth_carousel:
            for i in range(image_number):
                # carousel
                with ui.carousel_slide(str(i)).classes('-p0'):
                    carousel_image = Image.fromarray(LipAPI.mouth_images_buffer[i])
                    h, w = LipAPI.mouth_images_buffer[i].shape[:2]
                    img = ui.interactive_image(carousel_image.resize(size=(640, 360))).classes('w-[640]')
                    with img:
                        ui.button(text=str(i) + ':size:' + str(w) + 'x' + str(h), icon='tag') \
                            .props('flat fab color=white') \
                            .classes('absolute top-0 left-0 m-2') \
                            .tooltip('Image Number')
                # thumbs
                image = LipAPI.mouth_images_buffer[i]
                # Resize the image to the specified thumbnail width while maintaining aspect ratio
                height, width, _ = image.shape
                aspect_ratio = height / width
                new_height = int(LipAPI.thumbnail_width * aspect_ratio)
                resized_image = cv2.resize(image, (LipAPI.thumbnail_width, new_height))
                LipAPI.mouths_buffer_thumb.append(resized_image)  # add to list

            # set default image to X for preview
            LipAPI.mouth_carousel.set_value(str(get_index_from_letter('X')))

async def edit_mouth_time_buffer():
    """ json editor for mouth times populated from output file generated by audio analysis """

    def on_change(event):
        LipAPI.mouth_times_buffer = event.content['json']

    def save_data():
        with open(LipAPI.output_file + '.json', 'w', encoding='utf-8') as f:
            json.dump(LipAPI.mouth_times_buffer, f, ensure_ascii=False, indent=4)
            editor.update()

    if len(LipAPI.mouth_times_buffer) > 0:
        with ui.dialog() as dialog, ui.card():
            dialog.open()
            editor = ui.json_editor({'content': {'json': LipAPI.mouth_times_buffer}}, on_change=on_change)
            with ui.row():
                ui.button('save changes to file', on_click=save_data)
                ui.button('Exit', on_click=dialog.close)
    else:
        ui.notification('Nothing to edit... Maybe load/reload mouth data cue', position='center', type='warning')


async def wavesurfer():
    """
    This will run wavesurfer
    Display the waveform linked to audio player (using id)
    :return:
    """

    ui.add_css('''
    #waveform {
    margin: 0 28px; /* waveform */
    height: 148px; /* Set a height for the waveform */
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
        import WaveSurfer from 'https://unpkg.com/wavesurfer.js/dist/wavesurfer.esm.js';
        import TimelinePlugin from 'https://unpkg.com/wavesurfer.js/dist/plugins/timeline.esm.js';

        let wavesurfer;
        let cuePoints = [];
        let checkBlinkingInterval;

        const bottomTimeline = TimelinePlugin.create({
          height: 10,
          timeInterval: 5,
          primaryLabelInterval: 1,
          style: {
            fontSize: '8px',
            color: '#6A3274',
          },
        });

        function generateCuePointsFromContainer(containerId) {
            const container = document.getElementById(containerId);
            if (!container) {
                return [];
            }
            const cuePointElements = container.querySelectorAll('.cue-point');
            return Array.from(cuePointElements).map(cueElement => {
                const timeString = cueElement.id;
                return {
                    time: parseFloat(timeString),
                    id: timeString,
                    element: cueElement
                };
            });
        }

        function checkCuePointsAreaExistence(duration = 5000, interval = 100) {
            return new Promise((resolve) => {
                const startTime = Date.now();
                const checkInterval = setInterval(() => {
                    const elapsedTime = Date.now() - startTime;
        
                    // Check if the duration has been exceeded
                    if (elapsedTime > duration) {
                        clearInterval(checkInterval);
                        console.log('Time duration exceeded without finding the element.');
                        resolve(false);
                        return;
                    }
        
                    // Check if the CuePointsArea exists inside the CardMouth
                    const cardMouth = document.getElementById('CardMouth');
                    if (cardMouth) {
                        const cuePointsArea = cardMouth.querySelector('#CuePointsArea');
                        if (cuePointsArea) {
                            clearInterval(checkInterval);
                            console.log('CuePointsArea found.');
                            resolve(true);
                            return;
                        }
                    }
        
                    console.log('Checking for CuePointsArea...');
                }, interval);
            });
        }

        window.genCueData = function() {        

            // Check container exist
            checkCuePointsAreaExistence(10000, 500).then((found) => {
                if (found) {
                    console.log('CuePointsArea exists!');
                    cuePoints = generateCuePointsFromContainer('CuePoints');
                    console.log(`Number of cue points generated: ${cuePoints.length}`);
                } else {
                    console.log('CuePointsArea does not exist.');
                }
            });
        };

        function findNearestCuePoint(time) {
            if (cuePoints.length === 0) {
                return null;
            }
            const threshold = 1;
            let nearestCue = null;
            let smallestDiff = Infinity;

            cuePoints.forEach(cue => {
                const diff = Math.abs(time - cue.time);
                if (diff < smallestDiff && diff < threshold) {
                    smallestDiff = diff;
                    nearestCue = cue;
                }
            });

            return nearestCue;
        }

        function checkCuePoints() {
            const currentTime = wavesurfer.getCurrentTime();
            const threshold = 5;

            cuePoints.forEach(cue => {
                const cueElement = document.getElementById(cue.id);
                if (cueElement) {
                    if (Math.abs(currentTime - cue.time) < threshold) {
                        cueElement.classList.add('blink');
                    } else {
                        cueElement.classList.remove('blink');
                    }
                }
            });
        }

        async function initializeWavesurfer() {
            const audioElement = document.getElementById('player_vocals');
            audioElement.addEventListener('loadeddata', async function() {
                if (wavesurfer) {
                    wavesurfer.destroy();
                }

                wavesurfer = WaveSurfer.create({
                    container: '#waveform',
                    waveColor: 'violet',
                    progressColor: 'purple',
                    backend: 'MediaElement',
                    plugins: [bottomTimeline],
                });

                await wavesurfer.load(audioElement.src);
                wavesurfer.setVolume(0);

                audioElement.addEventListener('play', function() {
                    wavesurfer.play();
                });
                audioElement.addEventListener('pause', function() {
                    wavesurfer.pause();
                });
                audioElement.addEventListener('seeked', function() {
                    wavesurfer.seekTo(audioElement.currentTime / audioElement.duration);
                });
                audioElement.addEventListener('timeupdate', function() {
                    if (Math.abs(wavesurfer.getCurrentTime() - audioElement.currentTime) > 0.1) {
                        wavesurfer.seekTo(audioElement.currentTime);
                    }
                });

                document.getElementById('waveform').addEventListener('click', function(e) {
                    const waveformWidth = this.clientWidth;
                    const clickPosition = e.offsetX;
                    const progress = clickPosition / waveformWidth;
                    const newTime = (progress * audioElement.duration).toFixed(2);
                    audioElement.currentTime = parseFloat(newTime);
                    wavesurfer.seekTo(progress);

                    // console.log(newTime);
                    const nearestCue = findNearestCuePoint(newTime);
                    if (nearestCue) {
                        cuePoints.forEach(cue => {
                            const cueElement = document.getElementById(cue.id);
                            if (cueElement) {
                            cueElement.classList.remove('blink');
                            }
                        });
                        // console.log(nearestCue);
                        nearestCue.element.classList.add('blink');
                        const selectCue = document.getElementById(nearestCue.id)
                        if (selectCue) {
                            selectCue.focus({  preventScroll: false , focusVisible: true })
                            selectCue.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" })
                        }
                    } else {
                        // console.log('not found nearest');
                    }
                });
            });

            audioElement.addEventListener('error', function() {
                if (wavesurfer) {
                    wavesurfer.empty();
                }
            });
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            initializeWavesurfer();
        });

        function refresh_waveform(fileName) {
            const newSrc = fileName;
            updateAudioSource(newSrc);
        }

        async function updateAudioSource(newSrc) {
            const audioElement = document.getElementById('audio');
            audioElement.src = newSrc;
            await audioElement.load();
            initializeWavesurfer();
        }
    </script>
    
    ''')


@ui.page('/')
async def main():

    async def check_net_osc():
        return True

    async def check_net_wvs():
        return True

    async def check_net_status():
        print('net check status')

        if LipAPI.osc_client is not None:
            # check net status
            if check_net_osc:
                # set value depend on return code
                link_osc.props(remove="color=yellow")
                link_osc.props(add="color=green")
                link_osc.classes(add='animate-pulse')
            else:
                link_osc.props(remove="color=green")
                link_osc.props(add="color=red")

        if LipAPI.wvs_client is not None:
            # check net status
            if check_net_wvs:
                # set value depend on return code
                link_wvs.props(remove="color=yellow")
                link_wvs.props(add="color=green")
                link_wvs.classes(add='animate-pulse')
            else:
                link_wvs.props(remove="color=green")
                link_wvs.props(add="color=red")


    async def create_wvs_client():
        """ create / close WS client """
        print('WVS activation')

        if wvs_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.wvs_client is None:
                from WSClient import WebSocketClient
                ws_address = "ws://" + str(wvs_ip.value) + ":" + str(int(wvs_port.value)) + str(wvs_path.value)
                LipAPI.wvs_client = WebSocketClient(ws_address)
            # send init message
            wvs_msg = {'init: true'}
            if wvs_send_metadata.value is True:
                wvs_msg = str(LipAPI.mouth_times_buffer)
                wvs_send_metadata.value = False
            LipAPI.wvs_client.send_message(wvs_msg)
            # create or activate net timer
            if not LipAPI.net_status_timer:
                LipAPI.net_status_timer = ui.timer(5, check_net_status)
            else:
                LipAPI.net_status_timer.active = True

        else:
            # we stop the client
            LipAPI.wvs_client.stop()
            LipAPI.wvs_client = None
            link_wvs.props(remove="color=green")
            link_wvs.props(remove="color=red")
            link_wvs.classes(remove='animate-pulse')
            link_wvs.props(add="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.net_status_timer.active is True:
                if osc_activate.value is False:
                    print('stop timer')
                    LipAPI.net_status_timer.active = False

    async def create_osc_client():
        """ create / close OSC client """
        print('OSC activation')

        if osc_activate.value is True:
            # we need to create a client if not exist
            if LipAPI.osc_client is None:
                from OSCClient import OSCClient
                LipAPI.osc_client = OSCClient(str(osc_ip.value), int(osc_port.value))
            # send init message
            osc_msg = {'init: true'}
            if osc_send_metadata.value is True:
                osc_msg = str(LipAPI.mouth_times_buffer)
                osc_send_metadata.value = False
            LipAPI.osc_client.send_message(osc_address.value, osc_msg)
            # create or activate net timer
            if not LipAPI.net_status_timer:
                LipAPI.net_status_timer = ui.timer(5,check_net_status)
            else:
                LipAPI.net_status_timer.active=True

        else:
            # we stop the client
            LipAPI.osc_client.stop()
            LipAPI.osc_client = None
            link_osc.props(remove="color=green")
            link_osc.props(remove="color=red")
            link_osc.classes(remove='animate-pulse')
            link_osc.props(add="color=yellow")
            # if timer is active, stop it or not
            if LipAPI.net_status_timer.active is True:
                if wvs_activate.value is False:
                    print('stop timer')
                    LipAPI.net_status_timer.active=False


    def validate_file(file_name):
        load_mouth_button.disable()
        edit_mouth_button.disable()

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
        async def run_it():
            dialog.close()
            await set_file_name()

        with ui.dialog() as dialog, ui.card():
            dialog.open()
            ui.label('Are you sure ? ')
            with ui.row():
                ui.button('Yes', on_click=run_it)
                ui.button('No',on_click=dialog.close)


    async def set_file_name():
        """
        set file name from file input audio
        check if corresponding media entries exist
        """

        def file_alone():
            """ no stems """
            ui.notify(f'We will do analysis from audio source file {file_name}.')
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
        try:
            LipAPI.mouth_area_h.delete()
            LipAPI.mouth_times_buffer = {}
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

            else:
                # check if both mp3 files exist, if not so suppose not stems, manage from only source file
                if not os.path.isfile(file_folder + 'accompaniment.mp3') or \
                        not os.path.isfile(file_folder +'vocals.mp3'):

                    file_alone()

                else:
                    # stems
                    ui.notify('We will do analysis from stems files ...')
                    # specific case for vocals
                    if not os.path.isfile(file_folder + 'vocals.wav'):
                        # generate wav from mp3
                        utils.convert_audio(file_folder + 'vocals.mp3',file_folder + 'vocals.wav')
                        ui.notify('auto generate wav file')

                        # double check
                        if not os.path.isfile(file_folder + 'vocals.wav'):
                            ui.notification('ERROR on wav file creation', position='center', type='negative')
                            player_vocals.set_source('')
                            return

                    # set players
                    player_vocals.set_source(file_folder + 'vocals.mp3')
                    # this one is optional
                    player_accompaniment.set_source(file_folder + 'accompaniment.mp3')
                    LipAPI.file_to_analyse = file_folder + 'vocals.wav'

            # set params
            if audio_input.value != '':
                LipAPI.source_file = audio_input.value
            LipAPI.output_file = 'output/' + file
            LipAPI.audio_duration = None
            edit_mouth_button.enable()
            load_mouth_button.enable()

        else:

            audio_input.set_value('')


    async def analyse_pick_file() -> None:
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
        """ run audio analysis by rhubarb """

        def run_it():
            if rub._instance_running:
                ui.notification('Already running instance',type='negative', position='center')
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
                except:
                    pass
                LipAPI.mouth_times_buffer={}
                dialog.close()

        with ui.dialog() as dialog, ui.card():
            dialog.open()
            ui.label(f'Analyse file "{LipAPI.source_file}" with Rhubarb')
            ui.label('Are You Sure ?')
            with ui.row():
                ui.button('Yes', on_click=run_it)
                ui.button('No', on_click=dialog.close)


    async def load_mouth_cue():
        """ initiate mouth card cue creation """

        try:
            LipAPI.mouth_area_h.delete()
        except:
            pass

        LipAPI.mouth_times_buffer = {}

        if LipAPI.source_file != '':
            ui.notification('this could take some times .....',position='center', type='warning', spinner=True)

            if os.path.isfile(LipAPI.output_file + '.json'):
                with open(LipAPI.output_file + '.json', 'r') as data:
                    LipAPI.mouth_times_buffer = json.loads(data.read())

                ui.timer(1,generate_mouth_cue, once=True)

            else:
                ui.notify('No analysis file to read')
        else:
            ui.notify('Source file blank ... load a new file')


    async def load_mouth_model():
        """ load images from model into a carousel"""

        # delete if exist
        try:
            LipAPI.mouth_carousel.delete()
        except ValueError:
            pass
        # generate new one
        await create_mouth_model()
        # move it to card_right
        LipAPI.mouth_carousel.move(target_container=card_right)


    def find_nearest_cue_point(time, cue_points):
        """ find mouth card near time provided """

        if not cue_points or 'mouthCues' not in cue_points:
            return {"start": None ,"end": None ,"value": None }

        threshold = 5
        nearest_cue = {"start": None ,"end": None ,"value": None }
        smallest_diff = float('inf')

        for cue in cue_points['mouthCues']:
            diff = abs(time - cue['start'])
            if diff < smallest_diff and diff < threshold:
                smallest_diff = diff
                nearest_cue = {"start": cue['start'],"end": cue['end'],"value": cue['value'] }

        return nearest_cue


    async def run_gencuedata():
        """

        execute javascript function to generate
        data when click on waveform this focus on the mouth card

        """

        await ui.run_javascript('genCueData();', timeout=5)


    async def generate_mouth_cue():
        """ Generate graphical view of json file  could be time-consuming"""

        def position_player(seek_time, card, rem):
            """ put players to time """

            player_vocals.seek(float(seek_time))
            player_accompaniment.seek(float(seek_time))
            card.classes(remove='bg-cyan-700')
            card.classes(add='bg-red-400')
            rem.set_visibility(True)
            card.update()

        def set_default(card, rem):
            """ set time card to default color """

            card.classes(remove='bg-red-400')
            card.classes(add='bg-cyan-700')
            rem.set_visibility(False)
            card.update()

        # scroll area with timeline/images
        LipAPI.mouth_area_h = ui.scroll_area().classes('bg-cyan-700 w-400 h-40')
        LipAPI.mouth_area_h.props('id="CuePointsArea"')
        LipAPI.mouth_area_h.bind_visibility(LipAPI, 'mouth_cue_show')
        with LipAPI.mouth_area_h:
            all_rows_mouth_area_h = ui.row(wrap=False)
            all_rows_mouth_area_h.props('id=CuePoints')
            with all_rows_mouth_area_h:

                if len(LipAPI.mouth_images_buffer) == 9 and LipAPI.mouth_times_buffer.__len__() > 0:
                    mouth_cues = LipAPI.mouth_times_buffer['mouthCues']
                    for i in range(len(mouth_cues)):
                        start = mouth_cues[i]['start']
                        letter = mouth_cues[i]['value']
                        time_card = ui.card().classes(add="bg-cyan-700 cue-point")
                        time_card.props(f'id={start}')
                        with time_card:
                            ic_remove = ui.icon('highlight_off', size='xs')
                            ic_remove.style(add='cursor: pointer')
                            ic_remove.on('click', lambda card=time_card, rem=ic_remove: set_default(card, rem))
                            ic_remove.set_visibility(False)
                            avatar64 = 'data:image/jpeg;base64,' + utils.image_array_to_base64(
                                LipAPI.mouths_buffer_thumb[get_index_from_letter(letter)])
                            ui.interactive_image(avatar64).classes('w-10')
                            start = ui.label(start)
                            start.on('click',
                                     lambda st=start.text, card=time_card, rem = ic_remove: position_player(st, card, rem))
                            start.tooltip('Click to set player time')
                            start.style('cursor:grab')

                        letter = ui.label(letter)

        LipAPI.mouth_area_h.move(target_container=card_mouth)

        await ui.context.client.connected()

        # implement logic to bypass this by using config file (due slow computer as this is CPU intensive)
        # this could take some times
        ui.timer(1,run_gencuedata, once=True)

        edit_mouth_button.enable()
        load_mouth_button.enable()


    async def get_player_time():
        """
        get player current playing time
        """
        await ui.context.client.connected()
        current_play_time = await ui.run_javascript("document.querySelector('audio').currentTime;", timeout=3)
        return current_play_time


    async def player_time_action():
        """
        Retrieve current play time from the Player
        Set scroll area position
        Send WVS / OSC msg
        """
        play_time = await get_player_time()

        cue_record = find_nearest_cue_point(play_time, LipAPI.mouth_times_buffer)
        img_name = cue_record['value']

        # set new value to central label
        new_label = str(play_time) + ' | ' + str(img_name) + ' - ' + str(get_index_from_letter(img_name))
        time_label.set_text(new_label)

        # set the right image in carousel (letter)
        if LipAPI.mouth_carousel is not None:
            LipAPI.mouth_carousel.set_value(str(get_index_from_letter(img_name)))

        # scroll central mouth cues
        if LipAPI.player_status == 'play' and LipAPI.scroll_graphic is True:
            if LipAPI.audio_duration is None:
                LipAPI.audio_duration = await get_audio_duration('player_vocals')
            if LipAPI.mouth_area_h is not None:
                LipAPI.mouth_area_h.scroll_to(percent=((play_time*100)/LipAPI.audio_duration)/100, axis= 'horizontal')

        # send osc message
        if osc_activate.value is True:
            if LipAPI.player_status == 'play' or send_seek.value is True:
                LipAPI.osc_client.send_message(osc_address.value +'/mouthCue/' ,
                                               [play_time, cue_record['start'],cue_record['end'], img_name])

        # send wvs message
        if wvs_activate.value is True:
            if LipAPI.player_status == 'play' or send_seek.value is True:
                LipAPI.wvs_client.send_message(str([play_time, cue_record['start'],cue_record['end'], img_name]))


    def update_progress(data, is_stderr):
        """
        update circular progress when rhubarb working
        Caution: no ui action here, run from background ?????
        """
        if is_stderr:
            if 'value' in data:
                new_value = data['value']
                circular.set_value(new_value)
                if new_value == 1:
                    spinner_analysis.set_visibility(False)
                    load_model_button.enable()
                    edit_mouth_button.enable()
                    load_mouth_button.enable()
                    ok_button.enable()
                    print('Analysis Finished')

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
            ui.notify('Playing audio')
            spinner_vocals.set_visibility(True)

        elif event == 'pause':
            LipAPI.player_status = 'pause'
            ui.notify('Player on pause')
            if rub._instance_running is False:
                spinner_vocals.set_visibility(True)

    def event_player_accompaniment(event):
        """ action to player accompanied """

        if event == 'end':
            spinner_accompaniment.set_visibility(False)

        elif event == 'play':
            spinner_accompaniment.set_visibility(True)

        elif event == 'pause':
            spinner_accompaniment.set_visibility(False)

    #
    # create Rhubarb instance, callback will send back two values: data and is_stderr (for STDErr capture)
    #
    rub = RhubarbWrapper(callback=update_progress)

    #
    # Main UI generation
    #
    with ui.row(wrap=False).classes('w-full'):

        card_left = ui.card().tight().classes('w-full')
        card_left.set_visibility(True)
        with card_left:

            card_mouth = ui.card().classes('w-full')
            card_mouth.props('id="CardMouth"')
            with card_mouth:
                with ui.row():
                    ic_refresh = ui.icon('refresh')
                    ic_refresh.on('click', lambda : ui.navigate.to('/'))
                    mouth_cue_label = ui.label('File Name')
                    mouth_cue_label.bind_text_from(LipAPI, 'source_file')

                    #if LipAPI.source_file != '' and len(LipAPI.mouth_times_buffer) > 0:
                    #    await load_mouth_cue()

            waveform = ui.html('<div id=waveform ><div>')
            waveform.classes('w-full')
            waveform.bind_visibility(LipAPI,'wave_show')

            # time info
            with ui.row(wrap=False).classes('self-center'):
                time_icon = ui.icon('watch', size='xs')
                time_label = ui.label('0.0 X 0').classes('self-center')
                try:
                    if len(LipAPI.mouths_buffer_thumb) > 0:
                        model_img = Image.fromarray(LipAPI.mouths_buffer_thumb[0])
                    time_img = ui.image(model_img).classes('w-6')
                except:
                    pass

            with ui.row().classes('self-center'):

                ui.separator()

                with ui.column():
                    # player for vocals part, better mp3 file (wav made trouble as long to loading)
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
                control_area_v = ui.card(align_items='center').classes('w-44 h-52 border bg-cyan-900')
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
                    with ui.row():
                        ui.label('WVS')
                        link_wvs = ui.icon('link', size='xs', color='yellow')
                        link_osc = ui.icon('link', size='xs', color='yellow')
                        ui.label('OSC')

                # player 2
                with ui.column():
                    # player for musical part, need mp3 file
                    player_accompaniment = ui.audio('').props('id=player_accompaniment')
                    spinner_accompaniment = ui.spinner('audio', size='lg', color='green')
                    player_accompaniment.on('play', lambda:event_player_accompaniment('play'))
                    player_accompaniment.on('pause', lambda: event_player_accompaniment('pause'))
                    player_accompaniment.on('ended', lambda: event_player_accompaniment('end'))
                    spinner_accompaniment.set_visibility(False)
                    ui.label('ACCOMPANIMENT').classes('self-center')

            ui.separator()

            with ui.row():
                # Add an input field for the audio file name
                audio_input = ui.input(placeholder='Audio file to analyse', label='Audio File Name')
                audio_input.on('focusout',lambda: validate_file(audio_input.value))
                folder = ui.icon('folder', size='md', color='yellow')
                folder.style(add='cursor: pointer')
                # made necessary checks
                folder.on('click', lambda : analyse_pick_file())

                # Add an OK button to refresh the waveform and set all players and data
                ok_button = ui.button('OK', on_click=approve_set_file_name)
                ui.checkbox('Wave').bind_value(LipAPI,'wave_show')
                ui.checkbox('MouthCue').bind_value(LipAPI,'mouth_cue_show')

            ui.label(' ')

            with ui.row():
                def toggle_preview():
                    if LipAPI.mouth_carousel is not None:
                        if preview.value == 'Hide Preview':
                            card_right.set_visibility(False)
                        else:
                            LipAPI.mouth_carousel.set_value('8')
                            card_right.set_visibility(True)

                load_mouth_button = ui.button('Load MouthCue',on_click=load_mouth_cue)
                load_mouth_button.disable()
                edit_mouth_button = ui.button('Edit mouth Buffer', on_click=lambda: ui.navigate.to('/edit', new_tab=True))
                edit_mouth_button.disable()
                load_model_button = ui.button('Load a model', on_click=load_mouth_model)
                preview = ui.toggle(['Show Preview', 'Hide Preview'], value='Hide Preview', on_change=toggle_preview)


            if LipAPI.source_file != '':
                await set_file_name()

        with ui.card(align_items='center').tight().classes('self-center no-shadow no-border w-1/3') as card_right:
            await create_mouth_model()
            card_right.set_visibility(False)

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
            hide = ui.switch('Hide', on_change=lambda v: card_left.set_visibility(v.value))

        with ui.card().tight().classes('bg-cyan-400'):
            ui.label(' ')
            wvs_exp = ui.expansion('WledVideoSync').classes('bg-cyan-500')
            with wvs_exp:
                with ui.column():
                    wvs_ip = ui.input('Server IP', value='127.0.0.1')
                    with ui.row():
                        wvs_port = ui.number('Port', value=8000)
                        wvs_path = ui.input('Path (opt)', value='/ws')
                        wvs_activate = ui.checkbox('activate', on_change=create_wvs_client)
                        wvs_send_metadata = ui.checkbox('Metadata')

            ui.label(' ')
            ui.separator()

            osc_exp = ui.expansion('OSC').classes('bg-cyan-500')
            with osc_exp:
                with ui.column():
                    osc_address = ui.input('Address', value= '/WLEDLipSync')
                    osc_ip = ui.input('Server IP', value='127.0.0.1')
                    with ui.row():
                        osc_port = ui.number('Port', value=12000)
                        osc_activate = ui.checkbox('activate', on_change=create_osc_client)
                        osc_send_metadata = ui.checkbox('Metadata')

            ui.separator()

            send_seek = ui.checkbox('Send when Seek', value=True)

    await wavesurfer()

@ui.page('/edit')
async def edit_cue_buffer():

    await edit_mouth_time_buffer()

"""
app specific param
"""

app.add_media_files('/media', 'media')
app.add_static_files('/assets', 'assets')

"""
run niceGUI
"""
ui.run(native=False, reload=False, reconnect_timeout=15)
