# Bootstrap script for starting LedFx on Android
# Will first try to use external storage for config directory with fallback to dedicated app storage

import logging
import os
import sys

from android.storage import app_storage_path

from ports import WEBVIEW_PORT


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
    
    ledfx_main()
