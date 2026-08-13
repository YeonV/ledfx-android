# Wrapper for AudioSource.REMOTE_SUBMIX - the system's own internal audio
# output sink, protected by the signature|privileged CAPTURE_AUDIO_OUTPUT
# permission rather than by MediaProjection consent.
#
# This is the mechanism apps like screen recorders used before Android 10 added
# AudioPlaybackCapture for ordinary (non-privileged) apps: read the same shared
# sink every app writes its output into. There is no consent dialog because a
# regular app can never hold CAPTURE_AUDIO_OUTPUT in the first place - only an
# app installed in /system/priv-app AND explicitly whitelisted in a
# privapp-permissions XML can. That gate is entirely install-time; there is
# nothing left to prompt the user for at capture time.
#
# Structurally identical to AndroidAudioRecord (android_audiorecord.py) - same
# AudioPump-backed gapless capture, same block sizing rules. The only real
# difference is which AudioSource constant gets passed to AudioRecord().

import time
import logging
from jnius import autoclass

import android_pump

try:
    from android_playback_capture import AndroidPlaybackCapture as _Quantum
except Exception:  # API 29+ only; fall back to a plain 10 ms block
    _Quantum = None

logger = logging.getLogger(__name__)


class AndroidRemoteSubmix:
    """
    Class interface to AudioSource.REMOTE_SUBMIX.
    """

    name = 'System Audio (root)'
    hostapi = 'Android RemoteSubmix API'
    channels = 1
    sampling_rate = 48000
    pcm_bits = 16
    # read() blocks until a block is available, so the stream sets its own pace.
    paces_itself = True

    def __init__(self, session_id=0, capture_size=None):
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

    @staticmethod
    def is_supported():
        """
        REMOTE_SUBMIX itself has existed since API 19; what actually gates it is
        CAPTURE_AUDIO_OUTPUT, which the OS only grants at install time to a
        privileged system app. So the real test is whether that grant came
        through, not the API level - a non-privileged install would fail with
        SecurityException at AudioRecord construction, which is treated as
        "unsupported" here rather than surfaced as an error, so it simply does
        not appear as a usable device.
        """
        try:
            PackageManager = autoclass('android.content.pm.PackageManager')
            PythonService = autoclass('org.kivy.android.PythonService')
            service = PythonService.mService
            if service is None:
                return False
            perm = service.checkSelfPermission(
                'android.permission.CAPTURE_AUDIO_OUTPUT'
            )
            return perm == PackageManager.PERMISSION_GRANTED
        except Exception as exc:
            logger.debug('RemoteSubmix support check failed: %s', exc)
            return False

    def start(self):
        AudioRecord = autoclass('android.media.AudioRecord')
        AudioFormat = autoclass('android.media.AudioFormat')
        AudioSource = autoclass('android.media.MediaRecorder$AudioSource')

        audio_format = AudioFormat.ENCODING_PCM_16BIT
        channels = AudioFormat.CHANNEL_IN_MONO
        self.buffer_size = AudioRecord.getMinBufferSize(
            self.sampling_rate, channels, audio_format
        )

        # Same reasoning as AudioRecord: read exactly what LedFx asked for, not
        # a HAL-aligned size, or the resampler's out/in ratio silently shifts
        # the whole spectrum. HAL alignment comes from LedFx's sample_rate
        # setting instead; see native_frames_per_buffer().
        quantum = _Quantum.native_frames_per_buffer() if _Quantum else 480
        frames = self.capture_size or quantum
        self.frames_per_read = frames

        # Ring buffer: two blocks. Enough to absorb a GC pause, and every extra
        # block of headroom is latency the audio has to sit through.
        wanted = frames * 2 * 2  # 2 bytes/sample, 2 blocks
        if wanted > self.buffer_size:
            self.buffer_size = wanted

        logger.debug(f'Using RemoteSubmix buffer size: {self.buffer_size}')

        # This is the one line that actually differs from AndroidAudioRecord:
        # the source is the system's shared output mix, not the microphone.
        # If CAPTURE_AUDIO_OUTPUT was not really granted, this throws
        # SecurityException right here - fail loud, not a silent mic fallback.
        self.recorder = AudioRecord(
            AudioSource.REMOTE_SUBMIX,
            self.sampling_rate,
            channels,
            audio_format,
            self.buffer_size,
        )

        # Read exactly one block per call. read() blocks until that many bytes
        # are available, which paces the stream at LedFx's frame rate while
        # staying gapless.
        read_bytes = frames * 2
        self._waveform = bytearray(read_bytes)
        self.recorder.startRecording()
        self._pump = android_pump.make_pump(self.recorder, read_bytes, 3)
        logger.debug(
            'RemoteSubmix started: quantum=%s frames/read=%s (%.1f ms) ring=%s bytes',
            quantum, frames, 1000.0 * frames / self.sampling_rate, self.buffer_size,
        )
        return self

    def stop(self):
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
                logger.warning(f'Error stopping RemoteSubmix recorder: {e}')
            try:
                self.recorder.release()
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f'Error releasing RemoteSubmix recorder: {e}')
            self.recorder = None
            self._waveform = None
            logger.debug('RemoteSubmix stopped')

    @property
    def waveform(self):
        if self._pump is not None:
            raw = self._pump.take(500)
            if raw is None:
                if self._last_block is None:
                    raise RuntimeError('RemoteSubmix: no audio from pump')
                return self._last_block
            self._last_block = android_pump.to_bytes(raw)
            return self._last_block
        self.recorder.read(self._waveform, 0, len(self._waveform))
        return self._waveform
