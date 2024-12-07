import os
import subprocess
import json
import threading
import utils
import sys

from typing import Literal


def exe_name():
    if sys.platform.lower() == 'win32':
        return './rhubarb/win/Rhubarb-Lip-Sync-1.13.0-Windows/rhubarb.exe'
    elif sys.platform.lower() == 'linux':
        return './rhubarb/linux/Rhubarb-Lip-Sync-1.13.0-Linux/rhubarb'
    elif sys.platform.lower() == 'macos':
        return './rhubarb/mac/Rhubarb-Lip-Sync-1.13.0-macOS/rhubarb'
    else:
        return None

class RhubarbWrapper:
    """
    Wrapper class for the Rhubarb speech recognition tool, facilitating the execution of commands and handling output.
    This class manages the configuration and execution of the Rhubarb executable,
    allowing for various output formats and recognizer options.

    Attributes:
        _exe_name (str): The path to the Rhubarb executable.
        _instance_running (bool): Indicates whether an instance of Rhubarb is currently running.
        input_file (str): The input file for processing.
        lyrics_file (str): The lyrics file associated with the input.
        callback (callable): A callback function to handle output data.
        working_directory (str): The directory where the process will run.
        machineReadable (bool): Flag indicating if the output should be machine-readable.
        export_format (str): The format for the output file.
        consoleLevel (str): The level of console output.
        file_extension (str): The file extension based on the output format.
        output_file (str): The path for the output file.
        command (list): The command to be executed.
        return_code (int): The return code from the executed command.

    Methods:
        __init__: Initializes the RhubarbWrapper with specified parameters.
        _validate_export_format: Validates the specified export format.
        _validate_recognizer: Validates the specified recognizer type.
        run_command_in_subprocess: Constructs and runs the command in a subprocess.
        _read_output: Reads output from the subprocess and handles it.
        _handle_output: Processes a line of output, attempting to parse it as JSON.
        _wait_for_process: Waits for the subprocess to complete and updates the instance state.
        run: Starts the execution of the Rhubarb process with the specified files.

    """

    _exe_name = exe_name()
    _instance_running = False

    def __init__(self,
                 output_file: str = 'output/default',
                 export_format: Literal['dat', 'tsv', 'xml', 'json'] = 'json',
                 recognizer: Literal['pocketSphinx', 'phonetic'] = 'pocketSphinx',
                 machineReadable: bool = True,
                 callback=None,
                 working_directory: str = os.getcwd()):
        """
        Initializes a new instance of the RhubarbWrapper class with specified configuration options.
        This constructor sets up the necessary parameters for processing audio files and managing output formats.

        Args:
            output_file (str): The base name for the output file. Defaults to 'output/default'.
            export_format (Literal['dat', 'tsv', 'xml', 'json']): The format for the output file. Defaults to 'json'.
            recognizer (Literal['pocketSphinx', 'phonetic']): The speech recognizer to use. Defaults to 'pocketSphinx'.
            machineReadable (bool): Indicates if the output should be machine-readable. Defaults to True.
            callback (callable, optional): A callback function to handle output data. Defaults to None.
            working_directory (str): The directory where the process will operate.
            Defaults to the current working directory.

        Returns:
            None

        """
        self.input_file = ''
        self.lyrics_file = ''
        self.callback = callback
        self.working_directory = working_directory
        self.machineReadable = machineReadable
        self.export_format = export_format
        self._validate_export_format()
        self.recognizer = recognizer
        self._validate_recognizer()
        self.consoleLevel = 'Info'
        self.file_extension = f'.{self.export_format}'  # Set the file extension based on output_format
        self.output_file = output_file + self.file_extension
        self.command = []
        self.return_code = 0

    def _validate_export_format(self):
        """
        Validates the specified export format for the output file.
        This method checks if the export format is one of the allowed types and raises an error if it is not.

        Returns:
            None

        Raises:
            ValueError: If the export format is not one of 'dat', 'tsv', 'xml', or 'json'.

        """
        if self.export_format not in {'dat', 'tsv', 'xml', 'json'}:
            raise ValueError("output_format must be 'dat','tsv','xml','json'")

    def _validate_recognizer(self):
        """
        Validates the specified recognizer type for speech recognition.
        This method checks if the recognizer is one of the allowed types and raises an error if it is not.

        Returns:
            None

        Raises:
            ValueError: If the recognizer is not 'pocketSphinx' or 'phonetic'.

        """

        if self.recognizer not in {'pocketSphinx', 'phonetic'}:
            raise ValueError("recognizer must be 'pocketSphinx', 'phonetic'")

    def run_command_in_subprocess(self):
        """
        Constructs and executes a command in a subprocess to run the Rhubarb speech recognition tool.
        This method builds the command with the necessary parameters and starts the subprocess,
        handling output and process completion in separate threads.

        Returns:
            None

        """

        command = [RhubarbWrapper._exe_name, self.input_file]

        # Add arguments to the command
        if self.machineReadable:
            command.extend(['--machineReadable'])
        command.extend([f'-r {self.recognizer}', f'-f {self.export_format}'])
        if os.path.isfile(self.lyrics_file):
            command.extend([f'-d {self.lyrics_file}'])
        command.extend(
            [f'--consoleLevel {self.consoleLevel}', f'-o {self.output_file}']
        )
        self.command = command
        # Run the command in a separate process
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   cwd=self.working_directory)

        # Start threads to read stdout and stderr
        threading.Thread(target=self._read_output, args=(process.stdout, False)).start()
        threading.Thread(target=self._read_output, args=(process.stderr, True)).start()

        # Wait for the process to complete in a separate thread
        threading.Thread(target=self._wait_for_process, args=(process,)).start()

    def is_running(self):
        """Check if the instance is currently running.

        This method returns the status of the instance, indicating whether it is
        currently active or not.

        Returns:
            bool: True if the instance is running, False otherwise.
        """

        return self._instance_running

    def _read_output(self, pipe, is_error):
        """
        Reads output from a subprocess pipe and processes each line.
        This method continuously reads lines from the specified pipe and delegates the handling of each line
        to a designated output handler.

        Args:
            pipe (io.TextIOWrapper): The pipe from which to read output.
            is_error (bool): Indicates whether the output is from the error stream.

        Returns:
            None

        """

        for line in iter(pipe.readline, ''):
            self._handle_output(line.strip(), is_error)
        pipe.close()

    def _handle_output(self, line, is_stderr=False):
        """
        Processes a line of output from a subprocess, attempting to parse it as JSON.
        This method handles the parsed data by invoking a callback function if provided,
        and logger.infos the line if it cannot be decoded as JSON.

        Args:
            line (str): The output line to be processed.
            is_stderr (bool): Indicates whether the output is from the error stream. Defaults to False.

        Returns:
            None

        """

        try:
            data = json.loads(line)
            if self.callback is not None:
                self.callback(data, is_stderr)
        except json.JSONDecodeError:
            logger.info(f"msg: {line}")

    def _wait_for_process(self, process):
        """
        Waits for a subprocess to complete and updates the instance state accordingly.
        This method blocks until the specified process finishes,
        capturing its return code and indicating that the instance is no longer running.

        Args:
            process (subprocess.Popen): The subprocess to wait for.

        Returns:
            None

        """

        process.wait()
        self._instance_running = False
        self.return_code = process.returncode
        logger.info(f"Return code: {self.return_code} {self.command}")

    def run(self, file_name, dialog_file, output):
        """
        Starts the execution of the Rhubarb speech recognition process with the specified input and output files.
        This method initializes the necessary parameters and launches the subprocess in a separate thread,
        ensuring that only one instance can run at a time.

        Args:
            file_name (str): The name of the input file to be processed.
            dialog_file (str): The name of the lyrics file associated with the input.
            output (str): The base name for the output file.

        Returns:
            None

        Raises:
            RuntimeError: If an instance of Rhubarb is already running.

        """

        if self._instance_running:
            raise RuntimeError("An instance of Rhubarb is already running.")
        self.input_file = file_name
        self.lyrics_file = dialog_file
        self.output_file = output + self.file_extension
        self._instance_running = True  # Set the instance as running
        self.return_code = 999  # set default return code, if all Ok will be set to 0 after process finished
        run_thread = threading.Thread(target=self.run_command_in_subprocess)
        run_thread.daemon = True
        run_thread.start()

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
    logger = utils.setup_logging('config/logging.ini', 'WLEDLogger.rhubarb')

    lip_config = utils.read_config()

    # config keys
    server_config = lip_config[0]  # server key
    app_config = lip_config[1]  # app key
    color_config = lip_config[2]  # colors key
    custom_config = lip_config[3]  # custom key