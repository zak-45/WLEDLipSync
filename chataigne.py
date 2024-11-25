import os
import subprocess
import json
import sys
import threading
from typing import Literal

class ChataigneWrapper:
    """
    Simple Chataigne wrapper to run it from python

    command line arguments are :
    ./Chataigne [-r] [-f file] [-headless] [-forceGL / -forceNoGL] [<file>]
    -r  = reset preferences
    -f = open file (works also by adding the file name at the end without -f)
    -headless = run without gui (no window)
    forceGL / forceNoGL = force setting the "use opengl renderer" value, to use 3d acceleration or not
    (forceNoGL can be handy when having problem with graphics drivers)

    """

    if sys.platform.lower() == 'win32':
        _exe_name = './chataigne/win/chataigne.exe'
    elif sys.platform.lower() == 'linux':
        _exe_name = './chataigne/linux/chataigne'
    elif sys.platform.lower() == 'macos':
        _exe_name = './chataigne/mac/chataigne'
    _instance_running = False

    def __init__(self,
                 reset:bool = False,
                 load_file: str = '',
                 headless:bool = True,
                 open_gl: bool = True,
                 callback=None,
                 working_directory: str = os.getcwd()):

        self.reset = reset
        self.headless = headless
        self.open_gl = open_gl
        self.callback = callback
        if sys.platform.lower() == 'win32':
            self.working_directory = working_directory + '\chataigne\win'
        elif sys.platform.lower() == 'linux':
            self.working_directory = working_directory + '/chataigne/linux'
        elif sys.platform.lower() == 'macos':
            self.working_directory = working_directory + '/chataigne/mac'
        else:
            self.working_directory = working_directory
        self.load_file = self.working_directory + "/" + load_file
        self.command = []
        self.return_code = 0


    def run_command_in_subprocess(self):

        print(self.load_file)
        command = [ChataigneWrapper._exe_name, self.load_file]

        # Add arguments to the command
        if self.reset:
            command.extend(['-r'])
        if self.headless:
            command.extend(['-headless'])
        if self.open_gl:
            command.extend(['-forceGL'])
        else:
            command.extend(['-forceNoGL'])

        self.command = command
        # Run the command in a separate process
        process = subprocess.Popen(command,
                                   env=dict(os.environ, USERPROFILE=f"{self.working_directory}"),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   cwd=self.working_directory)

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

    def run(self, reset = False,  file_name = '', headless = True, open_gl = True):
        if self._instance_running:
            raise RuntimeError("An instance of Chataigne is already running.")
        self.load_file = self.working_directory + '/' + file_name
        self.reset = reset
        self.headless = headless
        self.open_gl = open_gl
        self._instance_running = True  # Set the instance as running
        self.return_code = 999  # set default return code, if all Ok will be set to 0 after process finished
        run_thread = threading.Thread(target=self.run_command_in_subprocess)
        run_thread.daemon = True
        run_thread.start()
