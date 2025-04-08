# dummy sentry_sdk module so ledfx.sentry_config.py doesn't throw an exception
# sentry_sdk library is not compatibile with android, nor does it makes sense to have in-app update checks

def init(*args, **kwargs):
    pass
