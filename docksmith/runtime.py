from __future__ import annotations
import os, shutil, tempfile
from . import store
from .isolation import run_in_container
from .layers import extract_layers

def run_container(name, tag, cmd_override=None, extra_env=None):
    store.init_store()
    manifest = store.load_manifest(name, tag)
    if manifest is None:
        raise RuntimeError(f"Image '{name}:{tag}' not found.")
    config = manifest.get("config", {})
    image_cmd = config.get("Cmd", [])
    workdir = config.get("WorkingDir") or "/"
    env_dict = _parse_env_list(config.get("Env", []))
    command = cmd_override if cmd_override else image_cmd
    if not command:
        raise RuntimeError(
            f"No CMD defined in image '{name}:{tag}' and no command given. "
            "Provide a command: docksmith run <image> <cmd>"
        )
    rootfs = tempfile.mkdtemp(prefix="docksmith_run_")
    try:
        layer_digests = [l["digest"] for l in manifest.get("layers", [])]
        extract_layers(layer_digests, rootfs, store.layer_path)
        os.makedirs(os.path.join(rootfs, workdir.lstrip("/")), exist_ok=True)
        exit_code = run_in_container(rootfs=rootfs, command=command, env=env_dict, workdir=workdir, extra_env=extra_env or {})
        print(f"\nContainer exited with code {exit_code}")
        return exit_code
    finally:
        shutil.rmtree(rootfs, ignore_errors=True)

def _parse_env_list(env_list):
    result = {}
    for item in env_list:
        if "=" in item:
            k, _, v = item.partition("=")
            result[k] = v
    return result
