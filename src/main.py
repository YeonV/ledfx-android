# Main ledfx-android entry point
# Requests permissions and kicks off LedFx service

import logging
import sys
import time
import threading

from jnius import autoclass, cast, java_method, PythonJavaClass
from android.broadcast import BroadcastReceiver
from android.permissions import check_permission, request_permissions, Permission

from ports import EXIT_APP_ACTION

logger = logging.getLogger('ledfx-android')

permissions_list = [
    Permission.RECORD_AUDIO,
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

    def exit_handler(context, intent):
        logger.info('Received exit signal. Stopping service and exiting.')
        # ServiceLedfx.stop() targets the generated class, so this actually
        # stops the running service.
        service.stop(mActivity)
        mActivity.finish()
        sys.exit()

    BroadcastReceiver(exit_handler, actions=[EXIT_APP_ACTION]).start()

    # Sleep this thread to let webview UI run while foreground service is running
    while True:
        time.sleep(1)
    

def validate_permissions():
    """Ensures all required permissions have been granted. If no, request them. If user denies, show a toast and shut down app.
    """
    
    event = threading.Event()
    
    def permissions_callback(permissions, results):
        # Ensure we have all required permissions to run LedFx
        if not all(results):
            
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

        event.set()

    # Trigger permission dialogues
    request_permissions(
        permissions_list,
        permissions_callback
    )
    
    # Wait for user to respond to permission requests
    event.wait()
    

if __name__ == '__main__':
    main()
