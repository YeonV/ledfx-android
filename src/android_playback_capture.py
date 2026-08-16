# Wrapper for the Android AudioPlaybackCapture API (Android 10 / API 29+).
#
# This is the only Android path that gives all three things at once: the OUTPUT
# MIX rather than the microphone, a CONTIGUOUS stream rather than snapshots, and
# 16-bit samples. Measured on a Pixel 8, the alternatives cost:
#
#   Visualizer   - output mix, but 8-bit, and the buffer only refreshes ~20 Hz
#                  (getMaxCaptureRate reports 20000 mHz). Polling faster returns
#                  byte-identical frames ~48% of the time, and roughly half the
#                  audio timeline is never seen at all.
#   AudioRecord  - contiguous and 16-bit, but it is the microphone: acoustic
#                  path, room noise, and silent on headphones.
#
# The cost here is consent. A MediaProjection can only be approved through an
# Activity, and LedFx's audio runs in the service process where there is no
# Activity. PythonActivity requests it and broadcasts the approved result to
# PythonService, which parks it in a static for this module to collect.

import time
import logging

from jnius import autoclass

import android_pump

logger = logging.getLogger(__name__)


class AndroidPlaybackCapture:
    """
    Class interface to AudioPlaybackCapture via MediaProjection.
    """

    name = 'Playback Capture'
    hostapi = 'Android PlaybackCapture API'
    channels = 1
    sampling_rate = 48000
    pcm_bits = 16
    # read() blocks until a block is available, so the stream sets its own pace.
    paces_itself = True

    # Building a MediaProjection consumes the approved result: a second attempt
    # with the same Intent throws. Hold the projection for the process lifetime
    # so restarting the stream does not require re-consent.
    _projection = None

    def __init__(self, capture_size=None):
        self.capture_size = capture_size
        self.recorder = None
        self._waveform = None
        self._pump = None
        self._last_block = None

    def __enter__(self, *args, **kwargs):
        return self.start()

    def __exit__(self, *args, **kwargs):
        self.stop()

    # ------------------------------------------------------------------
    @staticmethod
    def is_supported():
        """API 29+ only. Below that the class exists but can never start."""
        try:
            Build = autoclass('android.os.Build$VERSION')
            return Build.SDK_INT >= 29
        except Exception:
            return False

    @staticmethod
    def native_frames_per_buffer(default=480):
        """
        The device's HAL buffer quantum, in frames.

        Reads only in whole multiples of this can take the fast capture path;
        a size that straddles the quantum forces every read to span two HAL
        buffers and carries the extra latency for nothing. A Pixel 8 reports
        480 frames (10 ms at 48 kHz), while LedFx would otherwise ask for
        samplerate/fps = 800.
        """
        try:
            PythonService = autoclass('org.kivy.android.PythonService')
            Context = autoclass('android.content.Context')
            service = PythonService.mService
            if service is None:
                return default
            am = service.getSystemService(Context.AUDIO_SERVICE)
            raw = am.getProperty('android.media.property.OUTPUT_FRAMES_PER_BUFFER')
            value = int(raw) if raw else 0
            return value if value > 0 else default
        except Exception as exc:
            logger.debug('Could not read native frames per buffer: %s', exc)
            return default

    @staticmethod
    def align_to_quantum(frames, quantum):
        """Round up to a whole number of HAL buffers, never below one."""
        if quantum <= 0:
            return frames
        blocks = max(1, (int(frames) + quantum - 1) // quantum)
        return blocks * quantum

    @staticmethod
    def has_consent():
        """True once the user has approved a capture in the activity process."""
        try:
            PythonService = autoclass('org.kivy.android.PythonService')
            return bool(PythonService.hasMediaProjection())
        except Exception:
            return False

    @classmethod
    def _get_projection(cls):
        # Consumed here, not only from is_active()/the status endpoint: this
        # is the code path that actually rebuilds the capture, and it must
        # self-heal regardless of whether anything has polled status recently.
        # Without this, a stop (revoke, or the user via the system status-bar
        # control) followed by a fresh consent grant keeps handing back the
        # same dead cached object forever - the exact "even a fresh consent
        # grant... fails the exact same way forever" failure this class's
        # docstring already described, just now actually fixed instead of
        # only documented.
        if cls.stopped_externally():
            cls._projection = None

        if cls._projection is not None:
            return cls._projection

        PythonService = autoclass('org.kivy.android.PythonService')
        Context = autoclass('android.content.Context')

        service = PythonService.mService
        if service is None:
            raise RuntimeError('No service context; cannot build MediaProjection')

        result_code = PythonService.getMediaProjectionResultCode()
        result_data = PythonService.getMediaProjectionResultData()
        if not result_data or not result_code:
            raise RuntimeError(
                'No media projection consent yet. The UI must call '
                'LedFxAndroidBridge.requestPlaybackCapture() first.'
            )

        manager = service.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
        cls._projection = manager.getMediaProjection(result_code, result_data)
        PythonService.watchProjectionStop(cls._projection)
        logger.info('PlaybackCapture: MediaProjection acquired')
        return cls._projection

    @classmethod
    def stopped_externally(cls):
        """True once, consumed: whether the system has reported the session
        ended since the last check.

        Covers both causes the same way: the system dispatches onStop() to
        every registered callback identically whether this app called
        revoke() or the user stopped it via the system status-bar control -
        see MediaProjection.java's MediaProjectionCallback.Stub in AOSP.
        Consumed (not just read) so a single stop is only acted on once.
        """
        try:
            PythonService = autoclass('org.kivy.android.PythonService')
            return bool(PythonService.consumeProjectionStopped())
        except Exception:
            return False

    @classmethod
    def is_active(cls):
        """True if a live, still-valid projection is currently held."""
        if cls.stopped_externally():
            cls._projection = None
        return cls._projection is not None

    @classmethod
    def revoke(cls):
        """Fully end the MediaProjection session - not just this class's
        cached reference to it.

        The token is consumed by this: resuming afterward needs a fresh
        consent dialog, unlike switching to a different audio input and
        back, which reuses the cached projection for free (see the class
        docstring above _projection).
        """
        if cls._projection is not None:
            try:
                cls._projection.stop()
            except Exception as exc:
                logger.warning(
                    'PlaybackCapture: error stopping projection: %s', exc
                )
            cls._projection = None
        try:
            PythonService = autoclass('org.kivy.android.PythonService')
            PythonService.clearMediaProjection()
        except Exception as exc:
            logger.warning(
                'PlaybackCapture: error clearing stored consent: %s', exc
            )

    # ------------------------------------------------------------------
    def start(self):
        if not self.is_supported():
            raise RuntimeError('AudioPlaybackCapture requires Android 10 (API 29)')

        AudioFormat = autoclass('android.media.AudioFormat')
        AudioAttributes = autoclass('android.media.AudioAttributes')
        AudioRecord = autoclass('android.media.AudioRecord')
        AudioRecordBuilder = autoclass('android.media.AudioRecord$Builder')
        AudioFormatBuilder = autoclass('android.media.AudioFormat$Builder')
        CaptureConfigBuilder = autoclass(
            'android.media.AudioPlaybackCaptureConfiguration$Builder'
        )

        projection = self._get_projection()

        # Match what a media app actually plays. Without at least one matching
        # usage the recorder is created happily and then returns pure silence.
        # Apps that set ALLOW_CAPTURE_BY_NONE are excluded by the system and
        # there is no way around that - Spotify is the well known example.
        cfg = CaptureConfigBuilder(projection)
        cfg.addMatchingUsage(AudioAttributes.USAGE_MEDIA)
        cfg.addMatchingUsage(AudioAttributes.USAGE_GAME)
        cfg.addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
        capture_config = cfg.build()

        fmt = AudioFormatBuilder()
        fmt.setEncoding(AudioFormat.ENCODING_PCM_16BIT)
        fmt.setSampleRate(self.sampling_rate)
        fmt.setChannelMask(AudioFormat.CHANNEL_IN_MONO)
        audio_format = fmt.build()

        min_buf = AudioRecord.getMinBufferSize(
            self.sampling_rate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        # Read EXACTLY what LedFx asked for. Its callback resamples every block
        # to MIC_RATE // sample_rate samples using out/in as the ratio, so the
        # block is assumed to be precisely one frame period. Handing it a
        # different size silently time-stretches the audio and shifts the whole
        # spectrum - 480 frames where 800 is expected reads a 1 kHz tone as
        # 600 Hz. Alignment to the HAL quantum has to come from LedFx's
        # sample_rate instead; see native_frames_per_buffer().
        quantum = self.native_frames_per_buffer()
        frames = self.capture_size or quantum
        read_bytes = frames * 2  # 16-bit mono
        if quantum and frames % quantum:
            logger.info(
                'PlaybackCapture: block of %s frames straddles the %s-frame HAL '
                'quantum. Set LedFx audio sample_rate to %s for aligned, '
                'lower-latency reads.',
                frames, quantum, int(self.sampling_rate // quantum),
            )

        # Ring buffer: two blocks, not four. read() blocks until one block is
        # available, so a late frame waits here rather than being dropped - but
        # every block of headroom is also latency the audio has to sit through.
        # Two is the smallest that still absorbs a GC pause.
        buffer_size = max(min_buf, read_bytes * 2)
        self.frames_per_read = frames

        b = AudioRecordBuilder()
        b.setAudioFormat(audio_format)
        b.setBufferSizeInBytes(buffer_size)
        b.setAudioPlaybackCaptureConfig(capture_config)
        try:
            self.recorder = b.build()
        except Exception:
            # A MediaProjection token dies the moment the OS-level session
            # ends - e.g. the user tapping "Stop" on the system casting/
            # recording notification - and there is no callback telling us
            # that happened. Without clearing the cache here, every retry
            # (and even a fresh consent grant via the Settings button, since
            # _get_projection() checks this cache before ever looking at
            # PythonService's result holder) fails the exact same way
            # forever: AudioService logs "App passed invalid MediaProjection
            # token" and build() throws. Clearing it means the next start()
            # re-reads PythonService fresh, picking up a new grant if one has
            # been made, or correctly reporting "no consent yet" if not.
            type(self)._projection = None
            raise

        self._waveform = bytearray(read_bytes)
        self.recorder.startRecording()
        # Java-side drain at audio priority. Three blocks of headroom: enough to
        # ride out a GC pause, few enough that a stall costs freshness rather
        # than accumulating a backlog.
        self._pump = android_pump.make_pump(self.recorder, read_bytes, 3)
        logger.info(
            'PlaybackCapture started: sr=%s quantum=%s frames/read=%s (%.1f ms) '
            'min_buf=%s ring=%s bytes (%.1f ms)',
            self.sampling_rate, quantum, frames,
            1000.0 * frames / self.sampling_rate,
            min_buf, buffer_size,
            1000.0 * (buffer_size / 2) / self.sampling_rate,
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
                logger.warning(f'Error stopping playback capture: {e}')
            try:
                self.recorder.release()
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f'Error releasing playback capture: {e}')
            self.recorder = None
            self._waveform = None
            logger.debug('PlaybackCapture stopped')

    @property
    def waveform(self):
        """Raw little-endian 16-bit PCM, one block."""
        if self._pump is not None:
            # Timeout is generous rather than tight: it only has to notice a
            # wedged recorder, not pace the stream - the pump does that.
            raw = self._pump.take(500)
            if raw is None:
                # Nothing arrived. Repeat the previous block instead of handing
                # back a half-filled buffer, which would read as a click.
                if self._last_block is None:
                    raise RuntimeError('PlaybackCapture: no audio from pump')
                return self._last_block
            self._last_block = android_pump.to_bytes(raw)
            return self._last_block
        self.recorder.read(self._waveform, 0, len(self._waveform))
        return self._waveform
