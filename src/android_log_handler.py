from jnius import autoclass
import logging


class AndroidLogHandler(logging.Handler):
    """Custom logging handler to redirect logging messages to Android log so they can be viewed/filtered with logcat."""
    
    def __init__(self):
        super().__init__()
        self.log = autoclass('android.util.Log')
        self.level_map = {
            logging.NOTSET: self.log.v,
            logging.DEBUG: self.log.d,
            logging.INFO: self.log.i,
            logging.WARNING: self.log.w,
            logging.ERROR: self.log.e,
            logging.CRITICAL: self.log.e
        }

    def emit(self, record):
        log_entry = self.format(record)
        f = self.level_map.get(record.levelno, self.log.v)
        f(record.name, log_entry)
