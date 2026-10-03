"""Bounded download snapshots: one slot per user and kind, fixed five-minute TTL."""

import hashlib
import json
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import APIException

MAX_BYTES = settings.PLUGINS_CONFIG.get("netbox_agent_api", {}).get(
    "download_snapshot_max_bytes", 16 * 1024 * 1024
)
if type(MAX_BYTES) is not int or MAX_BYTES < 1:
    raise ImproperlyConfigured("download_snapshot_max_bytes must be a positive integer")
TTL = 300
BLOCK = 65536


class DownloadTooLarge(APIException):
    status_code = 413
    default_detail = "Download exceeds the configured snapshot limit; narrow the export or ask the operator to raise download_snapshot_max_bytes."


def bounded_bytes(chunks):
    parts = []
    size = 0
    for chunk in chunks:
        size += len(chunk)
        if size > MAX_BYTES:
            raise DownloadTooLarge()
        parts.append(chunk)
    return b"".join(parts)


class SnapshotChanged(APIException):
    status_code = 412
    default_detail = "Download snapshot expired or was replaced; restart the download."


def snapshot(user, kind, context, expected, produce, offset=0, length=8192):
    # Callers recheck access before this cache. Fixed per-user slots bound retained
    # bytes, while separate blocks avoid downloading the whole cache value per range.
    key = f"netbox-agent-download-v1:{kind}:{user.pk}"
    guard = hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()
    saved = cache.get(key) if expected else None
    if saved is None or saved["guard"] != guard:
        raw, metadata = produce()
        if len(raw) > MAX_BYTES:
            raise DownloadTooLarge()
        generation = uuid.uuid4().hex
        saved = {
            "guard": guard,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "generation": generation,
            **metadata,
        }
        for start in range(0, len(raw), BLOCK):
            cache.set(
                f"{key}:{start // BLOCK}",
                {"generation": generation, "raw": raw[start : start + BLOCK]},
                timeout=TTL,
            )
        cache.set(key, saved, timeout=TTL)
    end = min(offset + length, saved["size"])
    parts = []
    for index in range(offset // BLOCK, (end + BLOCK - 1) // BLOCK):
        block = cache.get(f"{key}:{index}")
        if block is None or block["generation"] != saved["generation"]:
            raise SnapshotChanged()
        start = index * BLOCK
        parts.append(block["raw"][max(0, offset - start) : min(BLOCK, end - start)])
    return {**saved, "chunk": b"".join(parts)}
