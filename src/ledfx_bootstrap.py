# Bootstrap script for starting LedFx on Android
# Will first try to use external storage for config directory with fallback to dedicated app storage

import logging
import os
import sys
import time

from android.storage import app_storage_path
from jnius import autoclass

from ports import EXIT_APP_ACTION, WEBVIEW_PORT

logger = logging.getLogger('ledfx-android')

# How long the service waits, after asking the activity to shut things down,
# before giving up and returning. See the note in start_ledfx().
EXIT_HANDOFF_TIMEOUT = 5


def use_bundled_certificates():
    """Make every default SSL context trust certifi's CA bundle.

    Android ships no CA store this OpenSSL build can read, so on a phone every
    outbound HTTPS request fails with CERTIFICATE_VERIFY_FAILED - failing
    album-art lookups being the visible symptom.

    Setting SSL_CERT_FILE is *not* enough here: measured on device, a context
    built after setting it still has an empty trust store, because
    set_default_verify_paths() does not load anything in this build. Only an
    explicit load_verify_locations() works, so default_certs loading is
    extended to do exactly that. The env var is set as well, for child
    processes and any library that reads it directly.

    Timing is the other half: aiohttp builds its default SSL context once, at
    import, and reuses it for every session afterwards. Run this before the
    ledfx import or it has no effect at all.
    """
    try:
        import certifi
    except ImportError:
        logger.warning('certifi not bundled; HTTPS requests will fail to verify')
        return

    cafile = certifi.where()
    if not os.path.isfile(cafile):
        logger.warning('certifi bundle missing at %s', cafile)
        return

    try:
        import ssl
    except ImportError:
        # Seen on a systemized (priv-app) install: Python's _ssl.so was built
        # against real OpenSSL, and a privileged app's linker namespace chains
        # through to /system/lib - where Android's libcrypto.so is BoringSSL,
        # a real API fork rather than a version bump (missing symbols like
        # OPENSSL_sk_pop_free confirm it, not just an ABI skew). Whichever one
        # ends up resident from zygote wins regardless of what the app bundles
        # alongside it, so there is no bundled-library fix from here - only
        # HTTPS verification degrades, not the rest of LedFx.
        logger.warning('ssl unavailable (%s); HTTPS requests will fail to verify', cafile)
        return

    os.environ.setdefault('SSL_CERT_FILE', cafile)

    if getattr(ssl.SSLContext, '_ledfx_certifi_patched', False):
        return

    original = ssl.SSLContext.load_default_certs

    def load_default_certs(self, purpose=ssl.Purpose.SERVER_AUTH):
        original(self, purpose)
        try:
            self.load_verify_locations(cafile=cafile)
        except Exception:
            logger.exception('Could not load bundled CA certificates')

    ssl.SSLContext.load_default_certs = load_default_certs
    ssl.SSLContext._ledfx_certifi_patched = True
    logger.info('Default SSL contexts now trust %s', cafile)


def start_ledfx():
    
    os.name = 'posix'  # Force os.name to 'posix' for compatibility
    sys.platform = 'linux'  # Force sys.platform to 'linux' for compatibility

    # Must precede the ledfx import: it pulls in aiohttp, which caches its
    # default SSL context on the way in.
    use_bundled_certificates()

    from ledfx.__main__ import main as ledfx_main
    
    # Reduce logging of noisy modules
    logging.getLogger('kivy.jnius.reflect').setLevel(logging.INFO)
    logging.getLogger('ledfx.api').setLevel(logging.INFO)
    
    sys.argv += [
        f'--config={app_storage_path()}',
        f'--port={WEBVIEW_PORT}',
        '--offline',
    ]
    
    # LedFx can shut itself down (Settings -> Shutdown hits /api/power), which
    # just returns from ledfx_main and ends the service. Without telling the
    # activity, the app is left running on a dead WebView.
    try:
        ledfx_main()
    except Exception:
        logger.exception('LedFx exited with an error. Service will restart automatically.')
    else:
        logger.info('LedFx exited cleanly. Signaling main activity to exit.')
        signal_main_activity_to_exit()

        # The service is declared sticky, so if we simply return here the OS
        # relaunches LedFx. Only an explicit stopService() clears that, so stay
        # alive until the activity's stop lands. This sleep normally does not
        # finish - the process is killed part-way through it - so the cost is
        # zero on the happy path. Reaching the line below means the handoff
        # failed and we fall back to the old (sticky-restart) behaviour.
        time.sleep(EXIT_HANDOFF_TIMEOUT)
        logger.warning(
            'Activity did not stop the service within %ss; returning anyway. '
            'The sticky flag will likely restart LedFx.',
            EXIT_HANDOFF_TIMEOUT,
        )


def signal_main_activity_to_exit():
    """Broadcast to the main activity that it should stop the service and close."""
    try:
        Intent = autoclass('android.content.Intent')
        PythonService = autoclass('org.kivy.android.PythonService')
        PythonService.mService.sendBroadcast(Intent(EXIT_APP_ACTION))
    except Exception:
        logger.exception('Failed to signal main activity to exit')
