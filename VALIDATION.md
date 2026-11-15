# Verification record

The full suite for this revision passed: **67 tests** using a pre-existing Python **3.9.6** environment from a neighboring checkout, invoked against this project directory. The five third-party PyMuPDF/SWIG deprecation warnings remain; no failures occurred. No environment or dependency installation was changed. This project has no local `.venv`; system Python has no pytest or project dependencies.

The real process test confirms initial sync is disabled, unauthenticated POST is rejected, an authenticated synthetic PDF is written/read back under its configured archive, another root is rejected, and a duplicate headless instance exits while the original remains running. It makes no IMAP or Notion network calls.

Also checked: browser JavaScript syntax with `node --check`; dry-run service output round-trips through `plistlib`; the Notion draft emits valid JSON with `enabled: false`. No LaunchAgent was installed. All allowlisted live-source files remained byte-identical after export work.

CI is configured for Python 3.10–3.13 on macOS/Ubuntu. That remote matrix has not yet run. Mail provider authentication, Linux desktop keyring integration, real user-supplied maps scripts, interactive folder/browser opening, macOS consent and live Notion write/readback require user-local configuration; they are not claimed as verified here.
