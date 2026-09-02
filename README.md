# Fuji mobile offline sync setup

Copy these two files into the `sibmel29/fuji-roadtrip` repository:

- `scripts/apply_mobile_sync_item.py`
- `.github/workflows/mobile-sync.yml`

The workflow receives `repository_dispatch` events of type `mobile_sync_item`.
All events are serialized by a concurrency group, applied to the same `mobile-sync`
branch, and accumulated in one open pull request named **Fuji mobile sync**.

Each item receives a deterministic SHA-256 fingerprint stored as `source_mobile_id`.
A retry of an identical queued item is therefore ignored instead of creating a duplicate.

After merging the mobile-sync PR, delete the `mobile-sync` branch. The next phone upload
will recreate it and open a fresh PR.

The MacroDroid capture macros do not require internet. Each category has five persistent
global queue slots (20 total). The universal uploader runs after reboot and every 5 minutes,
sending slots one at a time and clearing a slot only after GitHub returns HTTP 204.
