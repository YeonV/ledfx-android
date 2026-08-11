# Shared helper for the two continuous inputs (AudioRecord, PlaybackCapture).
#
# Both used to call AudioRecord.read() straight from the Python capture loop,
# which meant the drain only happened when the interpreter got round to it.
# org.kivy.android.AudioPump moves that read onto a Java thread at URGENT_AUDIO
# priority; this wraps it and falls back to the old direct read when the class
# is missing, so an older APK still works.

import logging

import numpy as np
from jnius import autoclass

logger = logging.getLogger(__name__)

try:
    _AudioPump = autoclass('org.kivy.android.AudioPump')
except Exception as exc:  # pragma: no cover - older bootstrap
    _AudioPump = None
    logger.info('AudioPump unavailable (%s); reading inline instead', exc)


def available():
    return _AudioPump is not None


def make_pump(recorder, block_bytes, capacity=3):
    """Start a Java-side drain, or None if the class is not in this build."""
    if _AudioPump is None:
        return None
    pump = _AudioPump(recorder, int(block_bytes), int(capacity))
    pump.start()
    logger.info(
        'AudioPump started: %s bytes/block, %s blocks of headroom',
        block_bytes, capacity,
    )
    return pump


def to_bytes(raw):
    """
    Normalise whatever pyjnius hands back for a Java byte[].

    Depending on the pyjnius build this is either a bytes object or a list of
    SIGNED ints, and bytearray() chokes on the negative values in the second
    case. int8 -> raw bytes round-trips both without caring which we got.
    """
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return np.array(raw, dtype=np.int8).tobytes()
