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

import os
import json
import time
import queue
import logging
import threading
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
        self._track = None
        self._echo_queue = None
        self._echo_thread = None
        self._echo_stop = None

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

        self._track = self._start_loopback_track(AudioFormat, audio_format, channels)

        logger.debug(
            'RemoteSubmix started: quantum=%s frames/read=%s (%.1f ms) ring=%s bytes',
            quantum, frames, 1000.0 * frames / self.sampling_rate, self.buffer_size,
        )
        return self

    def _native_duplication_active(self):
        """
        True if STREAM_MUSIC/MEDIA already reaches a real output device (not
        only remote_submix) without our help - i.e. this ROM's audio policy
        duplicates instead of exclusively redirecting. Measured directly:
        running our echo on top of that doesn't just waste CPU, it
        reintroduces the exact contention-driven stutter the echo has on
        weak hardware while adding nothing audible, since native duplication
        already covers it. Requires API 33 (getDevicesForAttributes);
        assumes no duplication below that, where the exclusive-redirect
        default is the far better documented, far more common case.
        """
        try:
            Build = autoclass('android.os.Build$VERSION')
            if Build.SDK_INT < 33:
                return False

            Context = autoclass('android.content.Context')
            AudioAttributes = autoclass('android.media.AudioAttributes')
            AudioAttributesBuilder = autoclass('android.media.AudioAttributes$Builder')
            AudioDeviceInfo = autoclass('android.media.AudioDeviceInfo')
            PythonService = autoclass('org.kivy.android.PythonService')

            service = PythonService.mService
            if service is None:
                return False
            audio_manager = service.getSystemService(Context.AUDIO_SERVICE)

            # Query the SAME usage a real media app uses (USAGE_MEDIA), not
            # our own USAGE_ALARM escape hatch - querying our own attrs would
            # trivially always show the speaker and tell us nothing.
            media_attrs = (
                AudioAttributesBuilder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build()
            )
            devices = audio_manager.getDevicesForAttributes(media_attrs)
            for i in range(devices.size()):
                if devices.get(i).getType() != AudioDeviceInfo.TYPE_REMOTE_SUBMIX:
                    return True
            return False
        except Exception:
            logger.exception('Could not check for native remote_submix duplication')
            return False

    def _echo_mode(self):
        """
        User override for whether to run the echo AudioTrack at all - "auto"
        (default), "on", or "off". Added because _native_duplication_active
        can be confidently wrong in a way the user can see before we can:
        without QUERY_AUDIO_STATE granted it fails safe and assumes the echo
        IS needed, which is exactly the state this device was in the moment
        a build requesting that permission had not been installed yet. This
        override lets a user fix that themselves rather than wait on a new
        build every time detection gets it wrong in either direction.

        Read directly from config.json rather than through a live
        ledfx/config reference: AndroidRemoteSubmix is constructed standalone
        by sounddevice.py's InputStream with no such reference threaded
        through, and reading the same file LedFx itself reads and writes
        avoids adding that plumbing for one setting. See
        remote_submix_echo.patch (applied to ledfx/effects/audio.py's
        AUDIO_CONFIG_SCHEMA) for where this key is actually declared.
        """
        try:
            from android.storage import app_storage_path
            path = os.path.join(app_storage_path(), 'config.json')
            with open(path, encoding='utf-8') as f:
                config = json.load(f)
            mode = config.get('audio', {}).get(
                'android_remote_submix_echo', 'auto'
            )
            return mode if mode in ('auto', 'on', 'off') else 'auto'
        except Exception:
            logger.debug(
                'Could not read echo mode override, defaulting to auto',
                exc_info=True,
            )
            return 'auto'

    def _start_loopback_track(self, AudioFormat, audio_format, channels):
        """
        REMOTE_SUBMIX is exclusive, not a tap: opening this AudioRecord makes
        Android's audio policy reroute STREAM_MUSIC away from the speaker and
        into the submix instead of also playing it locally (the same
        limitation pre-Android-10 privileged screen recorders had). Writing
        every captured block straight back out through our own AudioTrack is
        the workaround - the user hears LedFx's echo instead of the original
        app's now-silent output.

        USAGE_MEDIA was tried first and silently failed: it maps to
        STREAM_MUSIC, the exact stream this device's audio policy redirects
        into remote_submix while a capture client is open, so our own echo
        landed right back in the same virtual sink instead of the speaker
        (confirmed via dumpsys media.audio_flinger - our track's output
        thread had an AUDIO_DEVICE_OUT_REMOTE_SUBMIX patch). STREAM_ALARM was
        confirmed via dumpsys audio to still route to the physical speaker
        under the same conditions, so USAGE_ALARM is used to escape the
        redirect rather than fight it.

        Skipped when either the user has explicitly turned it off, or - on
        "auto", the default - a ROM/device is detected to already duplicate
        remote_submix natively (see _native_duplication_active): confirmed on
        device that running the echo unconditionally there just re-adds the
        same CPU-contention stutter for zero audible benefit.
        """
        mode = self._echo_mode()
        if mode == 'off':
            logger.info('RemoteSubmix: echo forced OFF by user setting')
            return None
        if mode == 'auto' and self._native_duplication_active():
            logger.info(
                'RemoteSubmix: STREAM_MUSIC already reaches a real output '
                'device without our help - native duplication detected, '
                'skipping the echo AudioTrack entirely.'
            )
            return None
        if mode == 'on':
            logger.info('RemoteSubmix: echo forced ON by user setting')
        try:
            AudioTrack = autoclass('android.media.AudioTrack')
            AudioTrackBuilder = autoclass('android.media.AudioTrack$Builder')
            AudioAttributes = autoclass('android.media.AudioAttributes')
            AudioAttributesBuilder = autoclass('android.media.AudioAttributes$Builder')
            AudioFormatBuilder = autoclass('android.media.AudioFormat$Builder')

            attrs = (
                AudioAttributesBuilder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build()
            )
            fmt = (
                AudioFormatBuilder()
                .setEncoding(audio_format)
                .setSampleRate(self.sampling_rate)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .build()
            )
            min_buf = AudioTrack.getMinBufferSize(
                self.sampling_rate, AudioFormat.CHANNEL_OUT_MONO, audio_format
            )
            # A ~40ms buffer (2 capture blocks) made sense for a low-latency
            # tap, but this CPU can't keep the pipeline running in real time
            # under load (Spotify decode + FFT/melbank + DDP output + this
            # echo, all contending for 4 old cores under the GIL) - sized for
            # low latency, it ran dry constantly, which is what "slow motion"
            # actually was: not literal pitch-shift, just the AudioTrack
            # starving and re-buffering over and over. Sizing for ~400ms of
            # slack trades latency for room to survive a hiccup without
            # running dry; for passively listening to music while LEDs react,
            # that lag is not noticeable the way starving every few blocks is.
            target_ms = 400
            target_bytes = int(self.sampling_rate * target_ms / 1000) * 2  # 16-bit mono
            echo_buffer_bytes = max(min_buf, target_bytes)
            track = (
                AudioTrackBuilder()
                .setAudioAttributes(attrs)
                .setAudioFormat(fmt)
                .setBufferSizeInBytes(echo_buffer_bytes)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
            )
            track.play()

            # Queue sized to match: enough blocks in flight that the worker
            # falling behind under contention drains a backlog instead of
            # immediately dropping blocks (which just starves the track
            # faster). Read_bytes isn't set yet at this point in start(), so
            # frames_per_read (set just above the call into here) is used.
            block_ms = 1000.0 * self.frames_per_read / self.sampling_rate
            queue_len = max(4, int(target_ms / block_ms))

            self._echo_stop = threading.Event()
            self._echo_queue = queue.Queue(maxsize=queue_len)
            self._echo_thread = threading.Thread(
                target=self._echo_worker, name='RemoteSubmixEcho', daemon=True
            )
            self._echo_thread.start()

            logger.debug(
                'RemoteSubmix loopback AudioTrack started (min_buf=%s buffer=%s queue=%s blocks)',
                min_buf, echo_buffer_bytes, queue_len,
            )
            return track
        except Exception:
            logger.exception('Could not start RemoteSubmix loopback playback; '
                              'speaker will stay silent while capturing')
            return None

    def _echo_worker(self):
        while not self._echo_stop.is_set():
            try:
                data = self._echo_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            track = self._track
            if track is None:
                continue
            try:
                track.write(data, 0, len(data), 1)  # WRITE_BLOCKING
            except Exception:
                logger.exception('RemoteSubmix loopback write failed')

    def stop(self):
        if self._pump is not None:
            try:
                self._pump.stop()
            except Exception as e:
                logger.warning(f'Error stopping audio pump: {e}')
            self._pump = None
        if self._echo_stop is not None:
            self._echo_stop.set()
        if self._echo_thread is not None:
            self._echo_thread.join(timeout=1.0)
            self._echo_thread = None
        self._echo_queue = None
        if self._track is not None:
            try:
                self._track.stop()
                self._track.release()
            except Exception as e:
                logger.warning(f'Error stopping loopback AudioTrack: {e}')
            self._track = None
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

    def _echo(self, data):
        # Non-blocking hand-off only: the actual (blocking) AudioTrack.write
        # happens on _echo_worker's own thread so it can never add latency
        # here. bytes(data) snapshots the non-pump path's reused bytearray -
        # without the copy the worker could read it after the next capture
        # has already overwritten it in place.
        if self._echo_queue is not None:
            try:
                self._echo_queue.put_nowait(bytes(data))
            except queue.Full:
                pass

    @property
    def waveform(self):
        if self._pump is not None:
            raw = self._pump.take(500)
            if raw is None:
                if self._last_block is None:
                    raise RuntimeError('RemoteSubmix: no audio from pump')
                return self._last_block
            self._last_block = android_pump.to_bytes(raw)
            self._echo(self._last_block)
            return self._last_block
        self.recorder.read(self._waveform, 0, len(self._waveform))
        self._echo(self._waveform)
        return self._waveform
