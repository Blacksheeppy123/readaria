"""Top-level core package marker.

MUST exist (even empty): without it, ``core`` is a PEP 420 namespace package,
and when ``/app/backend`` is on sys.path (backend.api.main appends it), the
regular package ``backend/core`` shadows the real
top-level ``core`` — every ``from core.config.settings import ...`` then fails
with ModuleNotFoundError in production images. See 2026-09-15 deploy incident.
"""
