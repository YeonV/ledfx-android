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

    Benchmarked on-device against the alternatives (numpy array construction,
    array.array with/without masking, memoryview): memoryview isn't supported
    at all here (raw doesn't expose the buffer protocol, so this is some kind
    of list-like jnius wrapper, not a real buffer), and every approach that
    iterates raw element-by-element in a Python-level loop (array.array with
    an `x & 0xFF` generator) was consistently the slowest - confirming the
    earlier finding that a manual masking loop is what made the first version
    of this function fall behind the pump in real time.

    bytes(raw) was both the fastest candidate AND, unexpectedly, never raised
    - meaning raw's elements are already in valid 0..255 range on this
    pyjnius build, so the numpy int8-overflow workaround this function used
    to need isn't actually necessary here. numpy is kept only as a fallback
    for a pyjnius build where bytes(raw) does raise (e.g. genuinely signed
    -128..-1 values with no masking).
    """
    try:
        return bytes(raw)
    except (ValueError, TypeError):
        return np.asarray(raw).astype(np.uint8).tobytes()
