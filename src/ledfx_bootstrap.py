# Bootstrap script for starting LedFx on Android
# Will first try to use external storage for config directory with fallback to dedicated app storage

import logging
import os
import sys
import time

from android.storage import app_storage_path
from jnius import autoclass

from ports import EXIT_APP_ACTION, WEBVIEW_PORT

logger = logging.getLogger('ledfx-android')

# How long the service waits, after asking the activity to shut things down,
# before giving up and returning. See the note in start_ledfx().
EXIT_HANDOFF_TIMEOUT = 5


def start_ledfx():
    
    os.name = 'posix'  # Force os.name to 'posix' for compatibility
    sys.platform = 'linux'  # Force sys.platform to 'linux' for compatibility
    
    from ledfx.__main__ import main as ledfx_main
    
    # Reduce logging of noisy modules
    logging.getLogger('kivy.jnius.reflect').setLevel(logging.INFO)
    logging.getLogger('ledfx.api').setLevel(logging.INFO)
    
    sys.argv += [
        f'--config={app_storage_path()}',
        f'--port={WEBVIEW_PORT}',
        '--offline',
    ]
    
    # LedFx can shut itself down (Settings -> Shutdown hits /api/power), which
    # just returns from ledfx_main and ends the service. Without telling the
    # activity, the app is left running on a dead WebView.
    try:
        ledfx_main()
    except Exception:
        logger.exception('LedFx exited with an error. Service will restart automatically.')
    else:
        logger.info('LedFx exited cleanly. Signaling main activity to exit.')
        signal_main_activity_to_exit()

        # The service is declared sticky, so if we simply return here the OS
        # relaunches LedFx. Only an explicit stopService() clears that, so stay
        # alive until the activity's stop lands. This sleep normally does not
        # finish - the process is killed part-way through it - so the cost is
        # zero on the happy path. Reaching the line below means the handoff
        # failed and we fall back to the old (sticky-restart) behaviour.
        time.sleep(EXIT_HANDOFF_TIMEOUT)
        logger.warning(
            'Activity did not stop the service within %ss; returning anyway. '
            'The sticky flag will likely restart LedFx.',
            EXIT_HANDOFF_TIMEOUT,
        )


def signal_main_activity_to_exit():
    """Broadcast to the main activity that it should stop the service and close."""
    try:
        Intent = autoclass('android.content.Intent')
        PythonService = autoclass('org.kivy.android.PythonService')
        PythonService.mService.sendBroadcast(Intent(EXIT_APP_ACTION))
    except Exception:
        logger.exception('Failed to signal main activity to exit')
