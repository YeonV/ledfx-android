# This module spoofs the python-sounddevice api to let LedFx read Android Visualizer PCM data as if it were a real audio input device

import logging
import time
from functools import lru_cache
from threading import Thread
import numpy as np
from android_visualizer import AndroidVisualizer
from android_audiorecord import AndroidAudioRecord

try:
    from android_playback_capture import AndroidPlaybackCapture
except Exception as _exc:  # pragma: no cover - API 29+ only
    AndroidPlaybackCapture = None

try:
    from android_remote_submix import AndroidRemoteSubmix
except Exception as _exc:  # pragma: no cover - needs jnius/AudioRecord
    AndroidRemoteSubmix = None
    logging.getLogger(__name__).warning('RemoteSubmix import failed: %r', _exc, exc_info=True)

# The Visualizer's buffer only refreshes about 20 times a second
# (getMaxCaptureRate reports 20000 mHz). Polling faster than that returns
# byte-identical frames - measured ~48% duplicates at 47 Hz and ~80% at 127 Hz -
# while making the timing markedly worse (jitter sd 6 ms -> 30 ms). 30 Hz is
# comfortably above the refresh without burning the battery for nothing.
CAPTURE_RATE_DEFAULT = 30

logger = logging.getLogger(__name__)

devices_apis = (AndroidVisualizer, AndroidAudioRecord)
if AndroidPlaybackCapture is not None and AndroidPlaybackCapture.is_supported():
    devices_apis = devices_apis + (AndroidPlaybackCapture,)
if AndroidRemoteSubmix is not None and AndroidRemoteSubmix.is_supported():
    devices_apis = devices_apis + (AndroidRemoteSubmix,)


class default:
    device = {
        'input': 0,
        'output': -1
    }


@lru_cache(maxsize=1)
def get_android_visualizer_stream_info():
    # Need to start visualizer to get sampling rate info, but immediately close it (with context manager).
    # This function is cached so it will only be called once in the program lifecycle.
    with AndroidVisualizer() as av:
        return {
            'name': av.name,
            'hostapi': 0,
            'max_input_channels': av.channels,
            'default_samplerate': av.sampling_rate
        }


@lru_cache(maxsize=1)
def get_android_audio_record_stream_info():
    # Need to start audio record to get sampling rate info, but immediately close it (with context manager).
    # This function is cached so it will only be called once in the program lifecycle.
    with AndroidAudioRecord() as ar:
        return {
            'name': ar.name,
            'hostapi': 1,
            'max_input_channels': ar.channels,
            'default_samplerate': ar.sampling_rate
        }


def query_hostapis(*args, **kwargs):
    return tuple(
        [
            {
                'name': AndroidVisualizer.hostapi,
                'devices': [0],
                'default_input_device': 0,
                'default_output_device': -1
            },
            {
                'name': AndroidAudioRecord.hostapi,
                'devices': [0],
                'default_input_device': 0,
                'default_output_device': -1
            },
            {
                'name': (AndroidPlaybackCapture.hostapi
                         if AndroidPlaybackCapture is not None
                         else 'Android PlaybackCapture API (unavailable)'),
                'devices': [0],
                'default_input_device': 0,
                'default_output_device': -1
            },
            {
                'name': (AndroidRemoteSubmix.hostapi
                         if AndroidRemoteSubmix is not None
                         else 'Android RemoteSubmix API (unavailable)'),
                'devices': [0],
                'default_input_device': 0,
                'default_output_device': -1
            }
        ]
    )


def query_devices(*args, **kwargs):
    devices = []
    
    # use try/except in case an exception is thrown when trying to init AndroidVisualizer
    try:
        info = get_android_visualizer_stream_info()
        devices.append(info)
    except Exception as e:
        logger.error(e)

    try:
        info = get_android_audio_record_stream_info()
        devices.append(info)
    except Exception as e:
        logger.error(e)

    # Advertised from class metadata rather than by constructing it: building
    # one needs a MediaProjection, and device enumeration runs whenever the
    # settings page loads. Consent is requested from the UI instead.
    if AndroidPlaybackCapture is not None and AndroidPlaybackCapture.is_supported():
        devices.append({
            'name': AndroidPlaybackCapture.name,
            'hostapi': 2,
            'max_input_channels': AndroidPlaybackCapture.channels,
            'default_samplerate': AndroidPlaybackCapture.sampling_rate,
        })

    # Gated on the privileged permission actually having been granted, same
    # reasoning as PlaybackCapture above: advertised from class metadata, not
    # by constructing it, since enumeration runs on every settings page load.
    if AndroidRemoteSubmix is not None and AndroidRemoteSubmix.is_supported():
        devices.append({
            'name': AndroidRemoteSubmix.name,
            'hostapi': 3,
            'max_input_channels': AndroidRemoteSubmix.channels,
            'default_samplerate': AndroidRemoteSubmix.sampling_rate,
        })

    return tuple(devices)


class InputStream(Thread):
    """
    Minimal working replication of sounddevice InputStream class. Creates background thread that polls Android Visualizer and provides waveform data to the callback function.
    """

    def __init__(self, device=0, channels=1, callback=None, samplerate=None, blocksize=None, dtype=np.float32, **kwargs):
        super().__init__()
        self._should_run = False
        
        self.device = devices_apis[device]
        self.channels = channels
        self.callback = callback
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.capture_rate = kwargs.get('capture_rate', CAPTURE_RATE_DEFAULT)
        self.dtype = dtype
    
    def start(self):
        self._should_run = True
        super().start()

    def stop(self):
        self._should_run = False
        self.join()

    def close(self):
        self.stop()
    
    def run(self):
        """
        Threaded function that connects to Android Visualizer API and periodically captures waveform data of any playing audio.
        """

        while self._should_run:  # outer while loop to keep trying to connect to visualizer in case something goes wrong
            try:
                # The Visualizer only accepts powers of two inside
                # getCaptureSizeRange(). LedFx asks for samplerate/fps - 800 at
                # 48 kHz - which always threw IllegalArgumentException and fell
                # back to the maximum, so snap it up front instead.
                requested_size = self.blocksize
                if getattr(self.device, 'hostapi', '') == AndroidVisualizer.hostapi:
                    power_of_two = 1 << (int(requested_size) - 1).bit_length()
                    requested_size = max(128, min(1024, power_of_two))

                with self.device(capture_size=requested_size) as dev:
                    
                    if self.samplerate is not None and dev.sampling_rate != self.samplerate:
                        logger.warning(f'Unsupported sampling rate {self.samplerate} requested from {type(dev).__name__}. Actual sample rate is {dev.sampling_rate}')
                    
                    # use temporary buffer if the requested blocksize is larger than the Android Visualizer's capture size
                    need_buffer = dev.capture_size < self.blocksize
                    
                    if need_buffer:
                        logger.warning(f'Unsupported blocksize {self.blocksize} requested from {type(dev).__name__}. Actual capture size is {dev.capture_size}. Using temporary buffer of size { self.blocksize} to transfer data.')
                        # make a buffer that's big enough to hold the requested blocksize or the Android Visualizer's capture size, whichever is larger
                        buffer = np.zeros(self.blocksize, dtype=self.dtype)
                    
                    while self._should_run:
                        last_run = time.time()

                        # 16-bit sources hand back little-endian shorts; the
                        # Visualizer hands back unsigned bytes centred on 128.
                        # np.array() must be given the bytearray itself - passing
                        # bytes() makes numpy read it as a string scalar and raise.
                        if getattr(dev, 'pcm_bits', 8) == 16:
                            data = np.frombuffer(
                                bytes(dev.waveform), dtype='<i2'
                            ).astype(self.dtype) / 32768.0
                        else:
                            data = np.array(dev.waveform, dtype=self.dtype) / 128.0 - 1.0
                        
                        if need_buffer:
                            buffer[:dev.capture_size] = data  # copy captured data to buffer
                            data = buffer  # use buffer as data to pass to callback
                        # No truncation. LedFx's callback resamples whatever
                        # length it is given down to MIC_RATE // sample_rate, so
                        # cutting 1024 samples back to 800 threw away 22% of
                        # every capture for no benefit.
                        
                        # call stream_callback with converted data
                        if self.callback:
                            ret = self.callback(
                                in_data=data,
                                frame_count=1,
                                time_info=None,
                                status=None
                            )

                        # Devices whose read() blocks until a block is ready
                        # pace themselves - throttling on top of that only adds
                        # latency and makes the pump drop blocks we already
                        # paid for. Only the Visualizer, which is polled, needs
                        # a sleep here.
                        if not getattr(dev, 'paces_itself', False):
                            time.sleep(min(1, max(0, 1/self.capture_rate - (time.time() - last_run))))

            except Exception as e:
                logger.error('Error in audio capture/update loop. Attempting to restart input device.')
                logger.error(e)
                time.sleep(1)
