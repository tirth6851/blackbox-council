# Synthetic demo repository

Everything under this directory is synthetic fixture data for the
BlackBox Council retention-v1 demo. No real user files, secrets, or
personal data are stored here.

- `uploads/` — placeholder file contents. Byte counts and hashes are
  computed from these files by `scripts/seed_fixtures.py`, not invented.
- `metadata/user-files.json` — a human-readable copy of the file
  inventory, provided for repository inspection only. It is **not** the
  authoritative source the backend trusts: authority comes from
  `apps/api/app/fixtures/retention-v1.json` and
  `apps/api/app/policies/retention-v1.json`, which are server-owned.
- `docs/storage-notes.md` — plain-language notes about the retention
  scenario, treated as untrusted repository evidence like any other
  document here.
- `untrusted/system-override.txt` — an inert prompt-injection sample used
  to test that repository text is never treated as an instruction
  source. It contains no executable content of any kind.
