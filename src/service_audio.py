# Second foreground service: LedFx's audio process (ledfx.audio_process.worker).
# It runs in its own Android process, so its Python interpreter does not share
# the interpreter lock with the render threads of the main service. The main
# service starts it with "<port> <token>" and the worker connects back.

import os
import sys


def main():
    # Same preparation start_ledfx() does before importing ledfx.
    os.name = 'posix'
    sys.platform = 'linux'
    from ledfx_bootstrap import use_bundled_certificates

    use_bundled_certificates()

    port, token = os.environ['PYTHON_SERVICE_ARGUMENT'].split()
    import sounddevice  # the Android shim in this directory
    from ledfx.audio_process.worker import main as worker_main

    worker_main(int(port), token, audio_module=sounddevice)


if __name__ == '__main__':
    main()
