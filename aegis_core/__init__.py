"""Aegis local executive workspace API and control-plane services.

Import ``create_app`` from :mod:`aegis_core.api` when starting the web service.
Keeping the package initializer side-effect free prevents database and policy
initialization during tooling, migrations, and unit-test collection.
"""

__all__: list[str] = []
