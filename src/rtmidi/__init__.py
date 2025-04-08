# dummy rtmidi module so ledfx devices/launchpad_lib.py doesn't throw an exception

class SystemError(Exception):
    pass

API_MACOSX_CORE = 0
API_LINUX_ALSA = 1
API_UNIX_JACK = 2
API_WINDOWS_MM = 3
API_RTMIDI_DUMMY = 4


def get_compiled_api():
    return []