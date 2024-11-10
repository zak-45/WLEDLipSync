import os
import subprocess
import json
import threading
from typing import Literal

class RhubarbWrapper:

    _exe_name = './rhubarb/win/rhubarb.exe'
    _instance_running = False

    def __init__(self,
                 output_file: str = 'output/default',
                 export_format: Literal['dat','tsv','xml','json'] = 'json',
                 recognizer: Literal['pocketSphinx', 'phonetic'] = 'pocketSphinx',
                 machineReadable: bool = True,
                 callback=None,
                 working_directory: str = os.getcwd()):

        self.input_file = ''
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
        if self.export_format not in {'dat','tsv','xml','json'}:
            raise ValueError("output_format must be 'dat','tsv','xml','json'")

    def _validate_recognizer(self):
        if self.recognizer not in {'pocketSphinx', 'phonetic'}:
            raise ValueError("recognizer must be 'pocketSphinx', 'phonetic'")


    def run_command_in_subprocess(self):

        command = [RhubarbWrapper._exe_name, self.input_file]

        # Add arguments to the command
        if self.machineReadable:
            command.extend(['--machineReadable'])
        command.extend([f'-r {self.recognizer}'])
        command.extend([f'-f {self.export_format}'])
        command.extend([f'--consoleLevel {self.consoleLevel}'])
        command.extend([f'-o {self.output_file}'])

        self.command = command
        # Run the command in a separate process
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.working_directory)

        # Start threads to read stdout and stderr
        threading.Thread(target=self._read_output, args=(process.stdout, False)).start()
        threading.Thread(target=self._read_output, args=(process.stderr, True)).start()

        # Wait for the process to complete in a separate thread
        threading.Thread(target=self._wait_for_process, args=(process,)).start()

    def _read_output(self, pipe, is_error):
        for line in iter(pipe.readline, ''):
            self._handle_output(line.strip(), is_error)
        pipe.close()

    def _handle_output(self, line, is_stderr=False):
        try:
            data = json.loads(line)
            if self.callback is not None:
                self.callback(data, is_stderr)
        except json.JSONDecodeError:
            print(f"msg: {line}")

    def _wait_for_process(self, process):
        process.wait()
        self._instance_running = False
        self.return_code = process.returncode
        print("Return code:", self.return_code, self.command)

    def run(self, file_name, output):
        if self._instance_running:
            raise RuntimeError("An instance of Rhubarb is already running.")
        self.input_file = file_name
        self.output_file = output + self.file_extension
        self._instance_running = True  # Set the instance as running
        self.return_code = 999  # set default return code, if all Ok will be set to 0 after process finished
        run_thread = threading.Thread(target=self.run_command_in_subprocess)
        run_thread.daemon = True
        run_thread.start()

