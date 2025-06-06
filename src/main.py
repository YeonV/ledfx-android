# Main ledfx-android entry point
# Requests permissions and kicks off LedFx service

import logging
import time
import threading

from jnius import autoclass, cast, java_method, PythonJavaClass
from android.permissions import check_permission, request_permissions, Permission

logger = logging.getLogger('ledfx-android')

permissions_list = [
    Permission.RECORD_AUDIO,
    Permission.MODIFY_AUDIO_SETTINGS,
    Permission.READ_EXTERNAL_STORAGE,
    Permission.WRITE_EXTERNAL_STORAGE,
    Permission.CAMERA,
]


def main():
    
    mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
    mActivity.mOpenExternalLinksInBrowser = True
    
    validate_permissions()
    
    small_icon = 'icon'
    title = 'LedFx'
    content = 'LedFx is running in the background'
    args = ''
    service = autoclass('com.ledfx.ledfx.ServiceLedfx')
    service.start(mActivity, small_icon, title, content, args)

    # Sleep this thread to let webview UI run while foreground service is running
    while True:
        time.sleep(1)


def validate_permissions():
    """Ensures all required permissions have been granted. If no, request them. If user denies, show a toast and shut down app.
    """
    
    event = threading.Event()  # use this to signal from lambda callback

    # Trigger permission dialogues
    request_permissions(
        permissions_list,
        lambda permissions, results: event.set()
    )
    
    # Wait for the lambda callback to be called. This happens after user accepts or rejects permission dialogues.
    event.wait()
    
    # Ensure we have all required permissions to run LedFx
    if not all([check_permission(p) for p in permissions_list]):
        
        Toast = autoclass('android.widget.Toast')
        String = autoclass('java.lang.String')
        mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
        msg = 'Please enable required permissions in app settings.'
        
        mActivity.runOnUiThread(
            lambda: Toast.makeText(
                mActivity,
                cast('java.lang.CharSequence', String(msg)),
                Toast.LENGTH_LONG
            ).show()
        )

        time.sleep(1)  # give the toast time to show
        
        # Shut down app
        raise RuntimeError('Required permissions not granted')
    

if __name__ == '__main__':
    main()
