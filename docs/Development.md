# Development, support and release

Python 3.10–3.14; Django5.2 LTS,6.0,6.1 within their Python compatibility ranges.
CI runs representative supported combinations plus PostgreSQL17 concurrent delivery.
Tests use real ORM migrations + SDK MockTransport + signed local fixtures, no Vatly
account writes. They cover all event permutations, rollback including outbox/audit,
duplicate delivery, purchase-key recovery, authorization, CSRF, billing identity,
status/grace rules and legacy/new subscription references. The isolated built wheel
test migrates a fresh DB, imports the package, and checks py.typed.

`.agents/setup` provisions pinned uv0.12.9 and Python3.12, syncs the lockfile and
runs Django system checks. It is executable/idempotent and needs no secrets/services.
It does not migrate a host application's DB or seed data. `vendor/` pins unmodified
unpublished dependency wheels; compare SHA256SUMS when refreshing them.

PyPI name `vatly-django` returned404 on 2026-11-09 (not a reservation). Import name
is `vatly_django`, version0.1.0a1. Before any release configure PyPI trusted publisher
owner `vatly`, repo `vatly-django`, workflow `release.yml`, environment `pypi`, with
required-reviewer protection on that GitHub environment. Publish SDK then Fluent
then Django. The release workflow builds/checks artifacts and only publishes on a
published GitHub release whose tag matches `v` plus the package version. No tag or
publication has been made. PyPI packages are public even if GitHub source is private.
