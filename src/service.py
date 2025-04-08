# This file will be run as a foregound service because we specify `foreground` attribute in buildozer.spec. We also specify `sticky` so service will restart by Android OS if it crashes.
# Foreground services have higher priority and are less likely to be paused by the system to reclaim memory.


def main():
    from ledfx_bootstrap import start_ledfx
    start_ledfx()


if __name__ == '__main__':
    main()
