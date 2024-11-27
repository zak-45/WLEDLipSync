import os
import subprocess
import json
import sys
import threading

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
        """
        Initializes a new instance of the class with specified configuration options.
        This constructor sets up the working environment and parameters for the instance.

        Args:
            reset (bool): Indicates whether to reset chataigne preference. Defaults to False.
            load_file (str): The name of the file to load. Defaults to an empty string.
            headless (bool): Specifies if the instance should run in headless mode (no GUI). Defaults to True.
            open_gl (bool): Indicates whether to enable OpenGL support. Defaults to True.
            callback (callable, optional): A callback function to be executed. Defaults to None.
            working_directory (str): The directory where the instance will operate. Defaults to the current working directory.

        """
        self.reset = reset
        self.headless = headless
        self.open_gl = open_gl
        self.callback = callback
        if sys.platform.lower() == 'win32':
            self.working_directory = working_directory + '\chataigne\win'
        elif sys.platform.lower() == 'linux':
            self.working_directory = f'{working_directory}/chataigne/linux'
        elif sys.platform.lower() == 'macos':
            self.working_directory = f'{working_directory}/chataigne/mac'
        else:
            self.working_directory = working_directory
        self.load_file = f"{self.working_directory}/{load_file}"
        self.command = []
        self.return_code = 0


    def run_command_in_subprocess(self):
        """
        Executes a command in a separate subprocess with the configured parameters.
        This method constructs the command based on the instance's settings and manages the execution
        in a way that allows for output handling.

        Returns:
            None

        """
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
        and prints the line if it cannot be decoded as JSON.

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
            print(f"msg: {line}")

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
        print("Return code:", self.return_code, self.command)

    def run(self, reset = False,  file_name = '', headless = True, open_gl = True):
        """
        Starts the execution of a subprocess with the specified parameters.
        This method initializes the necessary settings and launches the subprocess in a separate thread,
        ensuring that only one instance can run at a time.

        Args:
            reset (bool): Indicates whether to reset the instance. Defaults to False.
            file_name (str): The name of the file to load. Defaults to an empty string.
            headless (bool): Specifies if the instance should run in headless mode (no GUI). Defaults to True.
            open_gl (bool): Indicates whether to enable OpenGL support. Defaults to True.

        Returns:
            None

        Raises:
            RuntimeError: If an instance of Chataigne is already running.

        """
        if self._instance_running:
            raise RuntimeError("An instance of Chataigne is already running.")
        self.load_file = f'{self.working_directory}/{file_name}'
        self.reset = reset
        self.headless = headless
        self.open_gl = open_gl
        self._instance_running = True  # Set the instance as running
        self.return_code = 999  # set default return code, if all Ok will be set to 0 after process finished
        run_thread = threading.Thread(target=self.run_command_in_subprocess)
        run_thread.daemon = True
        run_thread.start()
