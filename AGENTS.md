# Pishow – Collections & Dedup (for maintainers/agents)

## Collections
- Each folder in `MEDIA_DIR` is a collection; subfolders are separate collections.
- Hidden folders/files (`.*`) and video preview files (suffix from `VIDEO_BACKGROUND_SUFFIX`) are ignored; `uploaded_raw` is ignored for collections/dedup.
- Selection:
  - Default: root `/` + `uploaded` (if present); edited in admin (`/admin` → default collections).
  - Device: chosen in `/go` or `/admin/{device}`; “Quick start” saves a single collection and rebuilds the queue; “Reset to default” restores defaults.
  - Queues rebuild when collections change (persistent `.pkl` in `storage`).
- Queue pulls keys only from active collections; duplicate keys are not repeated.

## Deduplication
- Goal: a file present in multiple collections is shown/stored once via **hardlink**.
- Triggers: `mark_change` on watchdog events (create/delete) and manual refresh in admin. On start, the service premarks “changed” to catch preexisting dupes.
- Run: background thread after `DEDUP_IDLE_SECONDS` idle (default 900s; if `DEBUG=true` — 60s). Skips if `storage/converter.lock` exists.
- Algorithm: SHA-256 hash; first file stays, others replaced with hardlink. Skips hidden files/folders, symlinks/hardlinks, video previews, `uploaded_raw`.
- Hardlinks are peer names; explorer shows full size per name, real disk usage is shared. Check via `fsutil hardlink list <file>` (Win) or `ls -li`/`stat` (Linux).
  - Hardlinks need the same filesystem/volume; cross-device duplicates are skipped (logged).

## Config snippets
- Env: `DEDUP_IDLE_SECONDS`, `DEBUG` (sets 60s idle), `MEDIA_DIR`, `VIDEO_BACKGROUND_SUFFIX`.
- Files/dirs: `storage/metadata.pkl` (duration cache), `storage/collections_default.pkl`, queues `storage/queue_<device>.pkl`.
