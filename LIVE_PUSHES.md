# Live device pushes (not committed anywhere)

`androdev.py file`/`push`/`stub` write straight to the device's filesystem via
`run-as`, bypassing git entirely - that is the point, it's the fast test loop.
The failure this file exists to prevent: answering "is everything
pushed/committed" from git status alone, while real, tested code sits here
instead, invisible to git, and getting forgotten before it matters (b38 shipped
without the thread-priority fix because of exactly this - nobody, including
Claude, checked for live-only state before answering "did you push
everything").

**Rule: before answering any "is everything committed/pushed/in" question,
read this file.** If it lists an entry for a `.py` change whose logic isn't
also present in a real commit in this repo (or `backend/`), say so explicitly
- don't let "I committed the things I meant to commit" pass for "everything is
in."

Appended automatically by `.claude/hooks/androdev-live-push-tracker.js` on
every `androdev.py file` invocation. Clear an entry (delete the line) once its
change has actually landed in a real commit - don't just let this grow forever.

---
<!-- All entries cleared 2026-08-17: virtuals.py/core.py priority boost -> thread_priority_boost.patch
     (LedFx-Builds), __main__.py logging gate -> android_quiet_logging.patch, events.py/core.py/melbank.py
     listener gating -> event_listener_gating.patch. The audio-analysis thread's own priority boost
     (sounddevice.py, this repo's src/) was live-pushed before this file/hook existed, so it was never
     logged here either - found only by diffing the on-device scratch copy against the real committed
     source. Now committed directly to src/sounddevice.py. -->
- 2026-11-15 TEMP instrumentation (manual root push, never commit): site-packages/ledfx/audio_process/client.py + worker.py ([instr-c]/[instr-w] timing prints, pull model) + protocol.py (single-frame reads, not instrumented); originals kept as client.pyc.orig / worker.pyc.orig / protocol.pyc.orig. Source now: scratchpad instr5/ (split timing; no switch interval, no boost). Remove by deleting the .py and renaming the .orig back.
- 2026-11-15 TEMP (manual root push): site-packages/ledfx/effects/audio.py = chain tree (main 28ad9d51 + Android chain) + option B non-blocking effect update (the B change itself is committed in _pipeline tools/audio_process.patch; this on-device copy goes when the next APK is installed); original kept as effects/audio.pyc.orig. Source: scratchpad chain/core. Remove by deleting the .py and renaming the .orig back.
