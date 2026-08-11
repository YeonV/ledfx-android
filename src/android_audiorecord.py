# Wrapper for the [Android AudioRecord API](https://developer.android.com/reference/android/media/AudioRecord)

import time
import logging
from jnius import autoclass

import android_pump

try:
    from android_playback_capture import AndroidPlaybackCapture as _Quantum
except Exception:  # API 29+ only; fall back to a plain 10 ms block
    _Quantum = None

logger = logging.getLogger(__name__)


class AndroidAudioRecord:
    """
    Class interface to the Android AudioRecord API
    """
    
    name = 'Microphone'
    hostapi = 'Android AudioRecord API'
    channels = 1
    sampling_rate = 48000  # native rate on modern devices; avoids a resample
    pcm_bits = 16          # 8-bit gave ~48 dB of range and audible quantisation
    # read() blocks until a block is available, so the stream sets its own pace.
    paces_itself = True

    def __init__(self, session_id=0, capture_size=None):
        """
        Initialize
        """
        self.session_id = session_id
        self.capture_size = capture_size
        self._waveform = None
        self.recorder = None
        self._pump = None
        self._last_block = None
        
    def __enter__(self, *args, **kwargs):
        return self.start()

    def __exit__(self, *args, **kwargs):
        self.stop()
    
    def start(self):
        """
        Configure native Android AudioRecord and start capture
        """
        AudioRecord = autoclass('android.media.AudioRecord')
        AudioFormat = autoclass('android.media.AudioFormat')
        AudioSource = autoclass('android.media.MediaRecorder$AudioSource')

        # Set parameters
        audio_format = AudioFormat.ENCODING_PCM_16BIT
        channels = AudioFormat.CHANNEL_IN_MONO
        self.buffer_size = AudioRecord.getMinBufferSize(
            self.sampling_rate,
            channels,
            audio_format
        )
        # Read exactly the block LedFx asked for. Its callback resamples every
        # block to a fixed length assuming the block is one frame period, so any
        # other size time-stretches the audio and shifts the whole spectrum.
        # HAL alignment has to come from LedFx's sample_rate instead.
        quantum = _Quantum.native_frames_per_buffer() if _Quantum else 480
        frames = self.capture_size or quantum
        self.frames_per_read = frames

        # Ring buffer: two blocks. Enough to absorb a GC pause, and every extra
        # block of headroom is latency the audio has to sit through.
        wanted = frames * 2 * 2   # 2 bytes/sample, 2 blocks
        if wanted > self.buffer_size:
            self.buffer_size = wanted

        logger.debug(f'Using AudioRecord buffer size: {self.buffer_size}')

        # Create AudioRecord instance
        self.recorder = AudioRecord(
            AudioSource.UNPROCESSED,
            self.sampling_rate,
            channels,
            audio_format,
            self.buffer_size
        )
        # Read exactly one block per call. read() blocks until that many bytes
        # are available, which paces the stream at LedFx's frame rate while
        # staying gapless - reading the whole ring instead forced ~24 Hz.
        read_bytes = frames * 2
        self._waveform = bytearray(read_bytes)
        self.recorder.startRecording()
        self._pump = android_pump.make_pump(self.recorder, read_bytes, 3)
        logger.debug(
            'AudioRecord started: quantum=%s frames/read=%s (%.1f ms) ring=%s bytes',
            quantum, frames, 1000.0 * frames / self.sampling_rate, self.buffer_size,
        )
        return self

    def stop(self):
        """
        Stop and release native Android AudioRecord
        """
        if self._pump is not None:
            try:
                self._pump.stop()
            except Exception as e:
                logger.warning(f'Error stopping audio pump: {e}')
            self._pump = None
        if self.recorder is not None:
            try:
                self.recorder.stop()
            except Exception as e:
                logger.warning(f'Error stopping AudioRecord: {e}')
            try:
                self.recorder.release()
                time.sleep(0.5)  # seems to improve stability to wait for a bit after releasing
            except Exception as e:
                logger.warning(f'Error releasing AudioRecord: {e}')
            self.recorder = None
            self._waveform = None
            logger.debug('AudioRecord stopped')
    
    @property
    def waveform(self):
        """
        Property for retrieving current PCM waveform data from AudioRecord
        """
        if self._pump is not None:
            raw = self._pump.take(500)
            if raw is None:
                if self._last_block is None:
                    raise RuntimeError('AudioRecord: no audio from pump')
                return self._last_block
            self._last_block = android_pump.to_bytes(raw)
            return self._last_block
        # Read PCM data into the buffer
        self.recorder.read(self._waveform, 0, len(self._waveform))
        return self._waveform
