"""Ship the memory service as a first-class client of a harness.

This package owns the installer logic: the harness registry, the payload that
lands in every surface the harness reads, and the plan/apply/verify/uninstall
path. ``scripts/harness/instalar.py`` and ``memory install`` are thin adapters
over :mod:`mcp_memory_service.installers.core`.
"""
