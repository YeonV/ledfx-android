# ledfx-android

This project is an Android port of the amazing [LedFx](https://github.com/LedFx/LedFx) audio reactive LED controller library, allowing visualization of **any audio** playing from your android device. Yes, that means Spotify, YouTube, mobile games, even system UI sounds! This project is intended to work on both mobile and Android TV devices.

## Android TV

Android TV devices like NVIDIA shield are often the central hub in a living room media experience. The original goal of this project was to enable LedFx here so it could visualize music from the apps I normally use to stream music (Spotify, YT, etc.) AND music that is cast to the Android TV box from my phone.

There are a few differences in building apps for mobile compared to Android TV, most importantly the fact that users interact with your app using a remote control rather than a touch screen or mouse/keyboard. Enter [Leanback Mode](https://developer.android.com/design/ui/tv/guides/foundations/design-for-tv). When running on Android TV, LedFx doesn't show its default UI but instead shows a QR code that points mobile devices to the LedFx server running on the Android TV device.

## Getting system audio into LedFx

The secret to visualizing **any** audio on your android device lies in the [Android Visualizer API](https://developer.android.com/reference/android/media/audiofx/Visualizer). This API exposes methods to access raw PCM waveform data of any audio currently playing from your device (at a reduced quality and capture rate). I found it adequate for LedFx visuals. LedFx typically relies on [python-sounddevice](https://github.com/spatialaudio/python-sounddevice/) for audio data input, which is build on PortAudio. Unfortunately PortAudio doesn't support Android. My solution was to write a mock sounddevice.py module to feed LedFx data from Android Visualizer API calls. This works for now, but is susceptible to upstream changes in the way LedFx interfaces with python-sounddevice.

## Quirks

### Android support of various LedFx dependencies

LedFx imports a few libraries that don't support Android. To make things work without any upstream changes to LedFx, I created minimal mock versions of these modules in the src directory with just enough content to make LedFx run. This is not a great solution long-term but works for now until changes can be made upstream to fix the problems for this project.

- rtmidi: Midi library for controlling devices connected to the computer via midi. Doesn't make sense to do this from Android TV devices. If upstream LedFx made libraries like this optional I wouldn't have to mock them here and everything would just work :)
- sentry_sdk: Handles automatic updates on PC. Android has its own mechanism for updating apps so this isn't needed. If upstream LedFx only imported this module when running in "online mode" I wouldn't have to mock it here.
- mss: Screen grabber. No android support. Ideally, upstream LedFx would add a try/catch around their programmatic imports of devices and effects so anything that fails to import simply doesn't show up in the dropdown lists.

### Hostname resolution

Some Android devices don't have mDNS support so auto discovery of WLED devices fails. I found that manually adding one by IP address works, then others are discovered and can be added as well. Could be helpful for upstream LedFx to fall back to IP address if hostname fails to resolve.

## Stack

The build system uses [Buildozer](https://github.com/kivy/buildozer) and [python-for-android](https://github.com/kivy/python-for-android/) which are part of the [Kivy](https://github.com/kivy/kivy) ecosystem.

Buildozer handles android build environment creation by automatically downloading required SDK, NDK, etc. First run will be slow because of this.

Python-for-android uses [recipes](https://python-for-android.readthedocs.io/en/latest/recipes.html) that tell the build system how to handle certain python libraries. This is necessary to help build libraries that have compiled components for the target architecture. The python-for-android project already has many recipes for common python libraries (like numpy) but some LedFx dependencies required custom or updated recipes. These can be found in the `recipes` folder. Aubio is one example of a library that required a custom recipe to get LedFx running on android.

## Getting started

- Clone this repo with submodules
  - `git clone --recurse-submodules --depth=1 https://github.com/broccoliboy/ledfx-android`
  - `deps/ledfx` is needed before we run buildozer so we have access to version info and icons that are used in the Android build.
- Optional: use a devcontainer
  - This repository includes a devcontainer recipe to quickly get up and running in a [VS Code devcontainer](https://code.visualstudio.com/docs/remote/containers) built around the [buildozer docker container](https://hub.docker.com/r/kivy/buildozer). This requires a local installation of Docker/Podman, but greatly simplifies development environment setup and works on any OS that supports Docker.
  - VS Code will automatically detect the devcontainer environment and ask if you want to reopen the folder in a container. Click yes, or use Ctrl/Cmd+Shift+P -> Remote-Containers: Open Workspace in Container...

### Build

- Use VS Code default build command
  - `Ctrl/Cmd + Shift + B`
    - Runs default build task defined in .vscode/tasks.json
    - Equivalent to `buildozer android debug`
- Other buildozer shell commands
  - `buildozer android debug` or `buildozer android release`
    - Builds apk in debug/release mode
  - `buildozer android clean`
    - Cleans build environment
- Optionally, set env var SKIP_PREREQUISITES_CHECK=1 on command line to speed up buildozer

See [here](https://github.com/kivy/buildozer) for more information on using the buildozer environment

## Future work

- Improve LedFx Leanback Mode to allow more controls, like triggering LedFx Scenes or setting effects on known devices.
- Automatic detection of music/audio playing using [Android Visualizer peak/RMS measurement mode](https://developer.android.com/reference/android/media/audiofx/Visualizer#getMeasurementPeakRms(android.media.audiofx.Visualizer.MeasurementPeakRms)) to enable/disable LedFx effects
