"""
store.py — manages ~/.docksmith/ on disk.

Directory layout:
  ~/.docksmith/
    images/   — one JSON manifest per image  (name:tag.json)
    layers/   — content-addressed tar files  (sha256:<hex>.tar)
    cache/    — cache-key → layer-digest     (cache_index.json)
"""

import hashlib
import json
import os
import shutil

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
IMAGES_DIR    = os.path.join(DOCKSMITH_DIR, "images")
LAYERS_DIR    = os.path.join(DOCKSMITH_DIR, "layers")
CACHE_DIR     = os.path.join(DOCKSMITH_DIR, "cache")
CACHE_INDEX   = os.path.join(CACHE_DIR, "cache_index.json")


def init_store():
    """Create ~/.docksmith directory tree if it doesn't exist."""
    for d in (IMAGES_DIR, LAYERS_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(CACHE_INDEX):
        _write_json(CACHE_INDEX, {})


# ── layer helpers ──────────────────────────────────────────────────────────────

def layer_path(digest: str) -> str:
    """Return the full path for a layer tar, given its digest string."""
    hex_part = digest.replace("sha256:", "")
    return os.path.join(LAYERS_DIR, f"sha256_{hex_part}.tar")


def store_layer(tmp_tar_path: str) -> str:
    """
    Hash tmp_tar_path, move it into layers/ under its digest, return digest.
    If a layer with the same digest already exists, the tmp file is removed.
    """
    digest = _sha256_file(tmp_tar_path)
    dest = layer_path(digest)
    if not os.path.exists(dest):
        shutil.move(tmp_tar_path, dest)
    else:
        os.remove(tmp_tar_path)
    return digest


def layer_exists(digest: str) -> bool:
    return os.path.exists(layer_path(digest))


def layer_size(digest: str) -> int:
    p = layer_path(digest)
    return os.path.getsize(p) if os.path.exists(p) else 0


# ── manifest helpers ───────────────────────────────────────────────────────────

def _manifest_path(name: str, tag: str) -> str:
    safe = f"{name.replace('/', '_')}_{tag}"
    return os.path.join(IMAGES_DIR, f"{safe}.json")


def save_manifest(manifest: dict) -> str:
    """
    Compute the manifest digest (with digest field = ""), write the file,
    return the final digest string.
    """
    # 1. Canonicalise with digest = ""
    m = dict(manifest)
    m["digest"] = ""
    canonical = json.dumps(m, sort_keys=True, separators=(",", ":"))
    hex_hash = hashlib.sha256(canonical.encode()).hexdigest()
    digest = f"sha256:{hex_hash}"

    # 2. Write with real digest
    m["digest"] = digest
    path = _manifest_path(m["name"], m["tag"])
    _write_json(path, m)
    return digest


def load_manifest(name: str, tag: str) -> dict | None:
    path = _manifest_path(name, tag)
    if not os.path.exists(path):
        return None
    return _read_json(path)


def list_manifests() -> list[dict]:
    manifests = []
    for fname in os.listdir(IMAGES_DIR):
        if fname.endswith(".json"):
            data = _read_json(os.path.join(IMAGES_DIR, fname))
            if data:
                manifests.append(data)
    return manifests


def delete_manifest(name: str, tag: str) -> list[str]:
    """
    Remove the manifest file and all layer files listed in it.
    Returns list of digests that were deleted.
    """
    manifest = load_manifest(name, tag)
    if manifest is None:
        raise FileNotFoundError(f"Image {name}:{tag} not found")

    deleted_digests = []
    for layer_entry in manifest.get("layers", []):
        d = layer_entry["digest"]
        p = layer_path(d)
        if os.path.exists(p):
            os.remove(p)
            deleted_digests.append(d)

    os.remove(_manifest_path(name, tag))
    return deleted_digests


# ── cache helpers ──────────────────────────────────────────────────────────────

def cache_lookup(cache_key: str) -> str | None:
    """Return stored layer digest for cache_key, or None on miss."""
    index = _read_json(CACHE_INDEX) or {}
    digest = index.get(cache_key)
    if digest and layer_exists(digest):
        return digest
    return None


def cache_store(cache_key: str, digest: str):
    """Record cache_key → digest in the index."""
    index = _read_json(CACHE_INDEX) or {}
    index[cache_key] = digest
    _write_json(CACHE_INDEX, index)


# ── internal helpers ───────────────────────────────────────────────────────────

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _write_json(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _read_json(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
