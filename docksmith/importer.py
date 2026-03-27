"""
importer.py — Import a pre-downloaded base image into the local store.

Usage:
  docksmith import <path-to-docker-tarball> <name:tag>

The tarball must be a Docker-format image tar (exported via docker save),
containing:
  manifest.json  — image manifest with layer paths
  <hash>/layer.tar  — layer archives

This runs ONCE during initial setup. No network during build/run.
"""

import json
import os
import shutil
import tarfile
import tempfile

from . import store
from .layers import extract_layers


def import_image(tarball_path: str, tag: str):
    """
    Import a Docker-format image tarball into ~/.docksmith/.

    Args:
        tarball_path: path to the .tar file from 'docker save'.
        tag:          'name:tag' to assign in the local store.
    """
    store.init_store()

    if ":" in tag:
        image_name, image_tag = tag.split(":", 1)
    else:
        image_name, image_tag = tag, "latest"

    tmp_dir = tempfile.mkdtemp(prefix="docksmith_import_")
    try:
        # Extract the tarball
        with tarfile.open(tarball_path, "r") as tf:
            tf.extractall(tmp_dir)

        # Read the Docker manifest.json
        manifest_path = os.path.join(tmp_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise ImportError(
                f"Not a valid Docker image tarball: no manifest.json in '{tarball_path}'"
            )

        with open(manifest_path) as f:
            docker_manifest = json.load(f)

        if not docker_manifest:
            raise ImportError("manifest.json is empty")

        image_entry = docker_manifest[0]
        layer_paths = image_entry.get("Layers", [])

        # Try to read config for ENV/CMD/WorkingDir
        config_file = image_entry.get("Config", "")
        image_config = {}
        if config_file:
            cfg_path = os.path.join(tmp_dir, config_file)
            if os.path.exists(cfg_path):
                with open(cfg_path) as f:
                    docker_config = json.load(f)
                image_config = docker_config.get("config", docker_config.get("Config", {}))

        env_list  = image_config.get("Env", []) or []
        cmd_list  = image_config.get("Cmd", []) or []
        workdir   = image_config.get("WorkingDir", "") or ""

        # Import each layer
        imported_layers = []
        for layer_rel in layer_paths:
            layer_tar = os.path.join(tmp_dir, layer_rel)
            if not os.path.exists(layer_tar):
                raise ImportError(f"Layer file not found: {layer_rel}")

            # Copy to a temp file, then store_layer moves it
            tmp_copy = tempfile.NamedTemporaryFile(delete=False, suffix=".tar")
            tmp_copy.close()
            shutil.copy2(layer_tar, tmp_copy.name)

            digest = store.store_layer(tmp_copy.name)
            imported_layers.append({
                "digest": digest,
                "size": store.layer_size(digest),
                "createdBy": f"imported from {os.path.basename(tarball_path)}",
            })
            print(f"  Imported layer {digest[:19]}... ({store.layer_size(digest)} bytes)")

        # Write the manifest
        manifest = {
            "name": image_name,
            "tag": image_tag,
            "digest": "",
            "created": _iso_now(),
            "config": {
                "Env": env_list,
                "Cmd": cmd_list,
                "WorkingDir": workdir,
            },
            "layers": imported_layers,
        }

        final_digest = store.save_manifest(manifest)
        short = final_digest.replace("sha256:", "")[:12]
        print(f"\nImported {image_name}:{image_tag}  sha256:{short}")
        print(f"  {len(imported_layers)} layer(s) stored in ~/.docksmith/layers/")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
