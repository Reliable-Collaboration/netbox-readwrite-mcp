"""Strict operator configuration. Paths in JSON are relative to that file."""

import ipaddress
import json
from pathlib import Path
from urllib.parse import urlparse


def validate_config(config):
    required = {"netbox_url", "token_file", "journal", "instance_id", "actor", "allowed_device_ids"}
    if not isinstance(config, dict) or set(config) != required:
        raise ValueError("Configuration requires exactly: " + ", ".join(sorted(required)))
    for key in required - {"allowed_device_ids"}:
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"Configuration {key} must be a non-empty string")
    ids = config["allowed_device_ids"]
    if not isinstance(ids, list) or not ids or any(type(v) is not int or v <= 0 for v in ids):
        raise ValueError("allowed_device_ids must be a non-empty list of positive integers")
    if len(set(ids)) != len(ids):
        raise ValueError("allowed_device_ids must not contain duplicates")
    url = urlparse(config["netbox_url"])
    try:
        local = ipaddress.ip_address(url.hostname or "").is_loopback
    except ValueError:
        local = url.hostname == "localhost"
    if url.scheme != "https" and not (url.scheme == "http" and local):
        raise ValueError("Use HTTPS for NetBox; HTTP is permitted only on loopback for a local lab")
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("NetBox URL must not contain credentials, a query, or a fragment")
    if url.path.rstrip("/").endswith("/api"):
        raise ValueError("netbox_url is the base URL, without the /api suffix")
    if Path(config["token_file"]).resolve() == Path(config["journal"]).resolve():
        raise ValueError("Token file and journal must be different files")
    return dict(config)


def load_config(path):
    path = Path(path).expanduser().resolve()
    config = json.loads(path.read_text())
    if isinstance(config, dict):
        for key in ("token_file", "journal"):
            if isinstance(config.get(key), str):
                value = Path(config[key]).expanduser()
                config[key] = str(value if value.is_absolute() else path.parent / value)
    return validate_config(config)
