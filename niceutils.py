"""
a: zak-45
d: 03/12/2024
v: 1.0.0.0

Nice Utilities for WLEDLipSync

"""

import logging
import concurrent_log_handler
import sys
import os
import cv2utils
import utils
import taglib

from nicegui import ui, events
from PIL import Image
from pathlib import Path
from typing import Optional


async def show_tags(file):
    """
    Asynchronously displays the tags of an audio file in a user interface dialog.
    This function opens a dialog that shows the tags in JSON format and includes a button to close the dialog.

    Args:
        file (str): The path to the audio file from which to extract tags.

    Returns:
        None
    """

    with taglib.File(file) as song:
        with ui.dialog() as tags_dialog, ui.card():
            tags_dialog.open()
            ui.json_editor({'content': {'json': song.tags}})
            ui.button('close', on_click=tags_dialog.close)


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


class LocalFilePicker(ui.dialog):
    """Local File Picker

    This is  simple file picker that allows you to select a file from the local filesystem where NiceGUI is running.
    Right-click on a file will display image if available.

    :param directory: The directory to start in.
    :param upper_limit: The directory to stop at (None: no limit, default: same as the starting directory).
    :param multiple: Whether to allow multiple files to be selected.
    :param show_hidden_files: Whether to show hidden files.
    :param thumbs : generate thumbnails
    """

    def __init__(self, directory: str, *,
                 upper_limit: Optional[str] = ...,
                 multiple: bool = False, show_hidden_files: bool = False, thumbs: bool = True) -> None:
        """
        Initializes a file selection interface for a specified directory.
        This interface allows users to browse and select files,
        with options for displaying hidden files and generating thumbnails.

        Args:
            directory (str): The path to the directory to browse.
            upper_limit (Optional[str], optional): An optional path that limits the selection to a specific directory.
                Defaults to None.
            multiple (bool, optional): If True, allows multiple file selection. Defaults to False.
            show_hidden_files (bool, optional): If True, displays hidden files in the directory. Defaults to False.
            thumbs (bool, optional): If True, generates thumbnails for image files. Defaults to True.

        Returns:
            None

        """
        super().__init__()

        self.drives_toggle = None
        self.path = Path(directory).expanduser()
        if upper_limit is None:
            self.upper_limit = None
        else:
            self.upper_limit = Path(directory if upper_limit == ... else upper_limit).expanduser()
        self.show_hidden_files = show_hidden_files
        self.supported_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')

        with (self, ui.card()):
            self.add_drives_toggle()
            self.grid = ui.aggrid({
                'columnDefs': [{'field': 'name', 'headerName': 'File'}],
                'rowSelection': 'multiple' if multiple else 'single',
            }, html_columns=[0]).classes('w-96').on('cellDoubleClicked', self.handle_double_click)

            # inform on right click
            self.grid.on('cellClicked', self.click)

            # open image or video thumb
            self.grid.on('cellContextMenu', self.right_click)

            with ui.row().classes('w-full justify-end'):
                ui.button('Cancel', on_click=self.close).props('outline')
                ui.button('Ok', on_click=self._handle_ok)

        self.update_grid()

        self.thumbs = thumbs

    def add_drives_toggle(self):
        """
        Adds a toggle interface for selecting available drives on Windows platforms.
        This function retrieves the logical drives and allows the user to switch between them,
        updating the current drive selection accordingly.

        Returns:
            None

        """
        if sys.platform.lower() == 'win32':
            import win32api
            drives = win32api.GetLogicalDriveStrings().split('\000')[:-1]
            self.drives_toggle = ui.toggle(drives, value=drives[0], on_change=self.update_drive)

    def update_drive(self):
        """
        Updates the current directory path based on the selected drive from the drives toggle.
        This function refreshes the file grid to reflect the contents of the newly selected drive.

        Returns:
            None

        """
        self.path = Path(self.drives_toggle.value).expanduser()
        self.update_grid()

    def update_grid(self) -> None:
        """
        Updates the file grid to display the contents of the current directory.
        This function retrieves the files and directories, applies filtering based on visibility settings,
        and sorts them for display in the grid.

        Returns:
            None

        """
        paths = list(self.path.glob('*'))
        if not self.show_hidden_files:
            paths = [p for p in paths if not p.name.startswith('.')]
        paths.sort(key=lambda p: p.name.lower())
        paths.sort(key=lambda p: not p.is_dir())

        self.grid.options['rowData'] = [
            {
                'name': f'📁 <strong>{p.name}</strong>' if p.is_dir() else p.name,
                'path': str(p),
            }
            for p in paths
        ]
        if self.upper_limit is None and self.path != self.path.parent or \
                self.upper_limit is not None and self.path != self.upper_limit:
            self.grid.options['rowData'].insert(0, {
                'name': '📁 <strong>..</strong>',
                'path': str(self.path.parent),
            })
        self.grid.update()

    def handle_double_click(self, e: events.GenericEventArguments) -> None:
        """
        Handles the event of a double click on a file or directory in the grid.
        This function updates the current path if a directory is double-clicked,
        or submits the selected file if a file is double-clicked.

        Args:
            e (events.GenericEventArguments): The event arguments containing information about the double-click event.

        Returns:
            None

        """
        self.path = Path(e.args['data']['path'])
        if self.path.is_dir():
            self.update_grid()
        else:
            self.submit([str(self.path)])

    async def _handle_ok(self):
        """
        Handles the confirmation action when the 'Ok' button is clicked.
        This asynchronous function retrieves the selected rows from the grid
        and submits their paths for further processing.

        Returns:
            None

        """
        rows = await self.grid.get_selected_rows()
        self.submit([r['path'] for r in rows])

    def click(self, e: events.GenericEventArguments) -> None:
        """
        Handles the click event on a file in the grid.
        This function checks if the clicked item is a supported file type and, if so,
        notifies the user to right-click for a preview.

        Args:
            e (events.GenericEventArguments): The event arguments containing information about the click event.

        Returns:
            None

        """
        self.path = Path(e.args['data']['path'])
        if self.path.suffix.lower() in self.supported_extensions and self.path.is_file() and self.thumbs:
            ui.notify('Right-click for Preview', position='top')

    async def right_click(self, e: events.GenericEventArguments) -> None:
        """
        Handles the right-click event on a file in the grid to display a thumbnail preview.
        This asynchronous function checks if the clicked item is a supported file type and, if so,
        extracts and displays a thumbnail from the image file.

        Args:
            e (events.GenericEventArguments): The event arguments containing information about the right-click event.

        Returns:
            None

        """
        self.path = Path(e.args['data']['path'])
        if self.path.suffix.lower() in self.supported_extensions and self.path.is_file() and self.thumbs:
            with ui.dialog() as thumb:
                thumb.open()
                with ui.card().classes('w-full'):
                    row = await self.grid.get_selected_row()
                    if row is not None:
                        extractor = cv2utils.VideoThumbnailExtractor(row['path'])
                        await extractor.extract_thumbnails(times_in_seconds=[5])  # Extract thumbnail at 5 seconds
                        thumbnails_frame = extractor.get_thumbnails()
                        img = Image.fromarray(thumbnails_frame[0])
                        ui.image(img)
                    ui.button('Close', on_click=thumb.close)


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
    logger = utils.setup_logging('config/logging.ini', 'WLEDLogger.niceutils')

    lip_config = utils.read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key
