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
- 2026-08-16T22:15:53.776Z `androdev.py file "Y:/tmp/virtuals_instrumented.py" "ledfx/virtuals.py"`
- 2026-08-16T22:29:44.764Z `androdev.py file "Y:/tmp/main_instrumented.py" "ledfx/__main__.py"`
- 2026-08-16T22:35:41.626Z `androdev.py file "Y:/tmp/virtuals_ondevice_current.py" "ledfx/virtuals.py"`
- 2026-08-16T22:59:49.914Z `androdev.py file "Y:/tmp/core_instrumented.py" "ledfx/core.py"`
- 2026-08-16T23:06:53.310Z `androdev.py file "Y:/tmp/events_instrumented.py" "ledfx/events.py"`
- 2026-08-16T23:16:18.819Z `androdev.py file "Y:/tmp/melbank_instrumented.py" "ledfx/effects/melbank.py"`
- 2026-08-16T23:39:26.850Z `androdev.py file "Y:/tmp/core_instrumented.py" "ledfx/core.py"`
- 2026-08-16T23:49:32.009Z `androdev.py file "Y:/tmp/main2_instrumented.py" "ledfx/__main__.py"`
