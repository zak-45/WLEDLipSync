import sys

from nicegui import ui, events
from PIL import Image
from pathlib import Path
from typing import Optional
import cv2utils

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
