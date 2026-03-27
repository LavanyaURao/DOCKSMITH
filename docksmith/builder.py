"""
builder.py — Build engine.

Reads a Docksmithfile, executes all instructions in isolation,
manages layers and cache, writes the final image manifest.

Build output format:
  Step 1/3 : FROM alpine:3.18
  Step 2/3 : COPY . /app [CACHE MISS] 0.09s
  Step 3/3 : RUN echo "build complete" [CACHE MISS] 3.82s
  Successfully built sha256:a3f9b2c1 myapp:latest (3.91s)
"""

import copy
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone

from . import store
from .cache import compute_cache_key
from .isolation import run_in_container
from .layers import copy_rootfs, create_copy_layer, create_run_layer, extract_layers
from .parser import (
    ParseError,
    parse_cmd,
    parse_copy,
    parse_docksmithfile,
    parse_env,
    parse_from,
)


def build(
    context_dir: str,
    tag: str,
    no_cache: bool = False,
) -> str:
    """
    Build an image from the Docksmithfile in context_dir.

    Args:
        context_dir: directory containing the Docksmithfile + build context.
        tag:         'name:tag' string for the resulting image.
        no_cache:    if True, skip all cache lookups and writes.

    Returns:
        The final image digest string.
    """
    store.init_store()

    docksmithfile = os.path.join(context_dir, "Docksmithfile")
    if not os.path.exists(docksmithfile):
        raise FileNotFoundError(f"No Docksmithfile found in '{context_dir}'")

    if ":" in tag:
        image_name, image_tag = tag.split(":", 1)
    else:
        image_name, image_tag = tag, "latest"

    instructions = parse_docksmithfile(docksmithfile)
    total = len(instructions)

    # ── build state ──
    layers: list[dict] = []          # [{digest, size, createdBy}]
    config = {
        "Env": [],
        "Cmd": [],
        "WorkingDir": "",
    }
    env_dict: dict[str, str] = {}    # current ENV accumulator
    workdir: str = ""                # current WORKDIR
    prev_digest: str = ""            # digest of last layer-producing step

    # For preserving created timestamp on full cache-hit rebuilds
    existing_manifest = store.load_manifest(image_name, image_tag)
    original_created = (
        existing_manifest.get("created") if existing_manifest else None
    )

    build_start = time.monotonic()
    total_time = 0.0
    cache_miss_triggered = False     # once true, all subsequent steps are misses

    for step_idx, instr in enumerate(instructions):
        keyword = instr["instruction"]
        args = instr["args"]
        raw_line = instr["raw"]
        step_num = step_idx + 1

        # ── FROM ──────────────────────────────────────────────────────────────
        if keyword == "FROM":
            base_name, base_tag = parse_from(args)
            print(f"Step {step_num}/{total} : FROM {args}")

            base_manifest = store.load_manifest(base_name, base_tag)
            if base_manifest is None:
                raise BuildError(
                    f"Base image '{base_name}:{base_tag}' not found in local store. "
                    "Import it first with: docksmith import <tarball> <name:tag>"
                )

            # Inherit base layers and config
            layers = list(base_manifest.get("layers", []))
            base_config = base_manifest.get("config", {})
            env_dict = dict(
                _parse_env_list(base_config.get("Env", []))
            )
            workdir = base_config.get("WorkingDir", "")
            config["Cmd"] = list(base_config.get("Cmd", []))

            # Previous digest = base manifest digest (for cache key chaining)
            prev_digest = base_manifest.get("digest", "")

            # If FROM changes, all downstream cache entries are invalidated
            # (handled naturally since prev_digest changes)

        # ── WORKDIR ───────────────────────────────────────────────────────────
        elif keyword == "WORKDIR":
            print(f"Step {step_num}/{total} : WORKDIR {args}")
            workdir = args
            config["WorkingDir"] = workdir

        # ── ENV ───────────────────────────────────────────────────────────────
        elif keyword == "ENV":
            print(f"Step {step_num}/{total} : ENV {args}")
            key, value = parse_env(args)
            env_dict[key] = value
            config["Env"] = _env_dict_to_list(env_dict)

        # ── CMD ───────────────────────────────────────────────────────────────
        elif keyword == "CMD":
            print(f"Step {step_num}/{total} : CMD {args}")
            config["Cmd"] = parse_cmd(args)

        # ── COPY ──────────────────────────────────────────────────────────────
        elif keyword == "COPY":
            src, dest = parse_copy(args)
            step_start = time.monotonic()

            # Compute file hashes for cache key (even if we'll miss)
            tmp_tar, file_hashes = create_copy_layer(context_dir, src, dest)

            cache_key = compute_cache_key(
                prev_digest, raw_line, workdir, env_dict, file_hashes
            )

            hit_digest = None
            if not no_cache and not cache_miss_triggered:
                hit_digest = store.cache_lookup(cache_key)

            if hit_digest:
                elapsed = time.monotonic() - step_start
                total_time += elapsed
                os.remove(tmp_tar)
                prev_digest = hit_digest
                layers.append({
                    "digest": hit_digest,
                    "size": store.layer_size(hit_digest),
                    "createdBy": raw_line,
                })
                print(f"Step {step_num}/{total} : COPY {args} [CACHE HIT] {elapsed:.2f}s")
            else:
                cache_miss_triggered = True
                digest = store.store_layer(tmp_tar)
                if not no_cache:
                    store.cache_store(cache_key, digest)
                elapsed = time.monotonic() - step_start
                total_time += elapsed
                prev_digest = digest
                layers.append({
                    "digest": digest,
                    "size": store.layer_size(digest),
                    "createdBy": raw_line,
                })
                print(f"Step {step_num}/{total} : COPY {args} [CACHE MISS] {elapsed:.2f}s")

        # ── RUN ───────────────────────────────────────────────────────────────
        elif keyword == "RUN":
            step_start = time.monotonic()

            cache_key = compute_cache_key(
                prev_digest, raw_line, workdir, env_dict, None
            )

            hit_digest = None
            if not no_cache and not cache_miss_triggered:
                hit_digest = store.cache_lookup(cache_key)

            if hit_digest:
                elapsed = time.monotonic() - step_start
                total_time += elapsed
                prev_digest = hit_digest
                layers.append({
                    "digest": hit_digest,
                    "size": store.layer_size(hit_digest),
                    "createdBy": raw_line,
                })
                print(f"Step {step_num}/{total} : RUN {args} [CACHE HIT] {elapsed:.2f}s")
            else:
                cache_miss_triggered = True
                # Extract all layers so far into a temp rootfs
                rootfs_before = tempfile.mkdtemp(prefix="docksmith_before_")
                rootfs_after  = tempfile.mkdtemp(prefix="docksmith_after_")

                try:
                    layer_digests = [l["digest"] for l in layers]
                    extract_layers(layer_digests, rootfs_before, store.layer_path)

                    # Copy before-state to after-state — RUN modifies after
                    copy_rootfs(rootfs_before, rootfs_after)

                    # Ensure WORKDIR exists in rootfs
                    if workdir:
                        wd_host = os.path.join(rootfs_after, workdir.lstrip("/"))
                        os.makedirs(wd_host, exist_ok=True)

                    # Run the command in isolation inside rootfs_after
                    rc = run_in_container(
                        rootfs=rootfs_after,
                        command=[args],
                        env=env_dict,
                        workdir=workdir or "/",
                    )
                    if rc != 0:
                        raise BuildError(
                            f"RUN '{args}' failed with exit code {rc}"
                        )

                    # Diff rootfs_before vs rootfs_after → delta tar
                    tmp_tar = create_run_layer(rootfs_before, rootfs_after)
                    digest = store.store_layer(tmp_tar)
                    if not no_cache:
                        store.cache_store(cache_key, digest)

                finally:
                    shutil.rmtree(rootfs_before, ignore_errors=True)
                    shutil.rmtree(rootfs_after, ignore_errors=True)

                elapsed = time.monotonic() - step_start
                total_time += elapsed
                prev_digest = digest
                layers.append({
                    "digest": digest,
                    "size": store.layer_size(digest),
                    "createdBy": raw_line,
                })
                print(f"Step {step_num}/{total} : RUN {args} [CACHE MISS] {elapsed:.2f}s")

    # ── Write manifest ─────────────────────────────────────────────────────────
    all_cache_hits = (not cache_miss_triggered) and (existing_manifest is not None)
    created = original_created if all_cache_hits and original_created else _iso_now()

    manifest = {
        "name": image_name,
        "tag": image_tag,
        "digest": "",          # filled by save_manifest
        "created": created,
        "config": {
            "Env": _env_dict_to_list(env_dict),
            "Cmd": config["Cmd"],
            "WorkingDir": config["WorkingDir"],
        },
        "layers": layers,
    }

    final_digest = store.save_manifest(manifest)
    short = final_digest.replace("sha256:", "")[:12]
    print(
        f"\nSuccessfully built sha256:{short} {image_name}:{image_tag} "
        f"({total_time:.2f}s)"
    )
    return final_digest


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_env_list(env_list: list[str]) -> list[tuple[str, str]]:
    """Convert ['KEY=val', ...] → [(key, val), ...]."""
    result = []
    for item in env_list:
        if "=" in item:
            k, _, v = item.partition("=")
            result.append((k, v))
    return result


def _env_dict_to_list(env_dict: dict[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in sorted(env_dict.items())]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BuildError(Exception):
    pass
