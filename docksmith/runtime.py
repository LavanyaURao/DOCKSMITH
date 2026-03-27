"""
runtime.py — Container runtime for `docksmith run`.

Assembles the image filesystem by extracting all layer tars in order,
then runs the command in isolation using the same primitive as RUN during build.
"""

import os
import shutil
import tempfile

from . import store
from .isolation import run_in_container
from .layers import extract_layers


def run_container(
    name: str,
    tag: str,
    cmd_override: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    """
    Assemble the image filesystem, run the container, return exit code.

    Args:
        name:         image name.
        tag:          image tag.
        cmd_override: overrides the image CMD if provided.
        extra_env:    {KEY: VALUE} from -e flags; overrides image ENV.
    """
    store.init_store()

    manifest = store.load_manifest(name, tag)
    if manifest is None:
        raise RuntimeError(f"Image '{name}:{tag}' not found.")

    config = manifest.get("config", {})
    image_cmd = config.get("Cmd", [])
    workdir   = config.get("WorkingDir") or "/"
    env_list  = config.get("Env", [])
    env_dict  = _parse_env_list(env_list)

    # Determine command to run
    command = cmd_override if cmd_override else image_cmd
    if not command:
        raise RuntimeError(
            f"No CMD defined in image '{name}:{tag}' and no command given. "
            "Provide a command: docksmith run <image> <cmd>"
        )

    # Extract all layers into a temp rootfs
    rootfs = tempfile.mkdtemp(prefix="docksmith_run_")
    try:
        layer_digests = [l["digest"] for l in manifest.get("layers", [])]
        extract_layers(layer_digests, rootfs, store.layer_path)

        # Ensure WORKDIR exists
        wd_host = os.path.join(rootfs, workdir.lstrip("/"))
        os.makedirs(wd_host, exist_ok=True)

        # Run
        exit_code = run_in_container(
            rootfs=rootfs,
            command=command,
            env=env_dict,
            workdir=workdir,
            extra_env=extra_env or {},
        )

        print(f"\nContainer exited with code {exit_code}")
        return exit_code

    finally:
        shutil.rmtree(rootfs, ignore_errors=True)


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_env_list(env_list: list[str]) -> dict[str, str]:
    result = {}
    for item in env_list:
        if "=" in item:
            k, _, v = item.partition("=")
            result[k] = v
    return result
