# This module spoofs the python-sounddevice api to let LedFx read Android Visualizer PCM data as if it were a real audio input device
import logging
import time
from functools import lru_cache
from threading import Thread

import numpy as np

from android_visualizer import AndroidVisualizer

CAPTURE_RATE_DEFAULT = 60

logger = logging.getLogger(__name__)

class default:
    device = {
        'input': 0,
        'output': -1
    }


@lru_cache(maxsize=1)
def get_android_visualizer_stream_info():
    # Need to start visualizer to get sampling rate info, but immediately close it (with context manager).
    # This function is cached so it will only be called in the program lifecycle.
    try:
        with AndroidVisualizer() as av:
            return {
                'name': av.name,
                'hostapi': 0,
                'max_input_channels': av.channels,
                'default_samplerate': av.sampling_rate
            }
    except Exception as e:
        logger.error(e)
        get_android_visualizer_stream_info.cache_clear()  # clear cache so future attempts will actually run instead of just returning None from cache


def query_hostapis(*args, **kwargs):
    return tuple([
        {
            'name': AndroidVisualizer.hostapi,
            'devices': [0],
            'default_input_device': 0,
            'default_output_device': -1
        }
    ])


def query_devices(*args, **kwargs):
    devices = []
    info = get_android_visualizer_stream_info()
    if info is not None:
        devices.append(info)
    return tuple(devices)


class InputStream(Thread):
    """
    Minimal working replication of sounddevice InputStream class. Creates background thread that polls Android Visualizer and provides waveform data to the callback function.
    """

    def __init__(self, callback=None, samplerate=None, blocksize=None, dtype=np.float32, **kwargs):
        super().__init__()
        self._should_run = False
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
                with AndroidVisualizer(capture_size=self.blocksize) as av:
                    
                    if self.samplerate is not None and av.sampling_rate != self.samplerate:
                        logger.error(f'Unsupported sampling rate {self.samplerate} requested from AndroidVisualizer. Actual samplerate is {av.sampling_rate}')
                    
                    # use temporary buffer if the requested blocksize is larger than the Android Visualizer's capture size
                    need_buffer = av.capture_size < self.blocksize
                    
                    if need_buffer:
                        logger.debug(f'Unsupported blocksize {self.blocksize} requested from AndroidVisualizer. Actual capture size is {av.capture_size}. Using temporary buffer of size { self.blocksize} to transfer data.')
                        # make a buffer that's big enough to hold the requested blocksize or the Android Visualizer's capture size, whichever is larger
                        buffer = np.zeros(self.blocksize, dtype=self.dtype)
                    
                    while self._should_run:
                        last_run = time.time()

                        # convert Android Visualizer data range [0, 255] to PortAudio float range [-1.0, 1.0]
                        data = np.array(av.waveform, dtype=self.dtype) / 128.0 - 1.0
                        
                        if need_buffer:
                            buffer[:av.capture_size] = data  # copy captured data to buffer
                            data = buffer  # use buffer as data to pass to callback
                        else:
                            data = data[:self.blocksize]  # make sure we're only passing the requested blocksize to callback
                        
                        # call stream_callback with converted data
                        if self.callback:
                            ret = self.callback(
                                in_data=data,
                                frame_count=1,
                                time_info=None,
                                status=None
                            )

                        # sleep some amount of time (constrained between 0 and 1 sec) to try to achieve desired capture rate
                        time.sleep(min(1, max(0, 1/self.capture_rate - (time.time() - last_run))))

            except Exception as e:
                logger.error('Error in visualizer capture/update loop. Attempting to restart Android Visualizer')
                logger.error(e)
                time.sleep(1)
