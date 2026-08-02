# Bootstrap script for starting LedFx on Android
# Will first try to use external storage for config directory with fallback to dedicated app storage

import logging
import os
import sys

from android.storage import app_storage_path
from jnius import autoclass

from ports import EXIT_APP_ACTION, WEBVIEW_PORT

logger = logging.getLogger('ledfx-android')


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


def signal_main_activity_to_exit():
    """Broadcast to the main activity that it should stop the service and close."""
    try:
        Intent = autoclass('android.content.Intent')
        PythonService = autoclass('org.kivy.android.PythonService')
        PythonService.mService.sendBroadcast(Intent(EXIT_APP_ACTION))
    except Exception:
        logger.exception('Failed to signal main activity to exit')
