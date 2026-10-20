- **Multi-harness installer: one command deposits the memory service across every surface a harness reads.**
  `scripts/harness/instalar.py` detects the harnesses present, prints the exact plan before writing, and
  deposits registration, steering and usage skill (plus the authoring hook on Hermes). It verifies the
  effect before claiming success, is idempotent, and `--uninstall` removes the server by key and only the
  files it created — a merged config is never deleted wholesale. `--root` allows an ad-hoc sandbox, so
  the installer can be exercised without touching a real installation. 13 tests.
