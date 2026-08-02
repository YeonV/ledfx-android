# Default port p4a webview uses (defined in buildozer.spec)
WEBVIEW_PORT = 8888

# Broadcast action the service uses to tell the activity that LedFx has stopped
# and the app should close. Lives here because it is a contract between two
# separate processes, and this module has no imports of its own to drag along.
EXIT_APP_ACTION = 'com.ledfx.EXIT_APP'

# # Alternate port for LedFx server to use if we're running on Android TV so webview can display simplified UI defined in leanback.py
# LEDFX_PORT_LEANBACK = 8888
