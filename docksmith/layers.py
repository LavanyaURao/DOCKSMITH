"""
layers.py — Create deterministic tar-delta layers for COPY and RUN steps.

Key rules from the spec:
  - Tar entries added in lexicographically sorted path order
  - File timestamps zeroed (mtime = 0) for reproducibility
  - Layer = only the files added/modified by that step (a delta, not a snapshot)
"""

import fnmatch
import hashlib
import io
import os
import shutil
import tarfile
import tempfile


# ── COPY layer ─────────────────────────────────────────────────────────────────

def create_copy_layer(context_dir: str, src_pattern: str, dest: str) -> tuple[str, dict[str, str]]:
    """
    Copy files matching src_pattern (glob) from context_dir into a tar
    rooted at dest.

    Returns:
      (tmp_tar_path, {rel_path: sha256_hex, ...})
    """
    matched = _glob_files(context_dir, src_pattern)
    if not matched:
        raise FileNotFoundError(
            f"COPY: no files matched pattern '{src_pattern}' in context '{context_dir}'"
        )

    file_hashes: dict[str, str] = {}
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar")
    tmp.close()

    with tarfile.open(tmp.name, "w") as tf:
        for rel_path in sorted(matched):
            abs_path = os.path.join(context_dir, rel_path)

            # Skip symlinks and non-regular files in build context
            if not os.path.isfile(abs_path) or os.path.islink(abs_path):
                continue

            file_hashes[rel_path] = _sha256_file(abs_path)

            if dest.endswith("/") or os.path.isdir(abs_path):
                arc_name = dest.rstrip("/") + "/" + rel_path
            else:
                arc_name = dest

            arc_name = arc_name.lstrip("/")

            info = tarfile.TarInfo(name=arc_name)
            with open(abs_path, "rb") as fh:
                data = fh.read()
            info.size  = len(data)
            info.mtime = 0
            info.mode  = 0o644
            info.type  = tarfile.REGTYPE
            tf.addfile(info, io.BytesIO(data))

    return tmp.name, file_hashes


# ── RUN layer ──────────────────────────────────────────────────────────────────

def copy_rootfs(src: str, dst: str):
    """
    Copy src to dst preserving symlinks (including dangling ones).

    Uses symlinks=True so dangling symlinks (pointing to paths that only
    exist inside a Linux rootfs, e.g. /etc/alternatives/awk) don't cause
    'No such file or directory' on Mac.
    """
    shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)


def create_run_layer(rootfs_before: str, rootfs_after: str) -> str:
    """
    Diff rootfs_before vs rootfs_after and produce a tar of changed regular files.
    Returns tmp_tar_path.
    """
    before_files = _scan_dir(rootfs_before)
    after_files  = _scan_dir(rootfs_after)

    changed: list[str] = []
    for rel_path, after_hash in after_files.items():
        before_hash = before_files.get(rel_path)
        if before_hash != after_hash:
            changed.append(rel_path)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar")
    tmp.close()

    with tarfile.open(tmp.name, "w") as tf:
        for rel_path in sorted(changed):
            abs_path = os.path.join(rootfs_after, rel_path)
            if not os.path.isfile(abs_path) or os.path.islink(abs_path):
                continue
            info = tarfile.TarInfo(name=rel_path.lstrip("/"))
            with open(abs_path, "rb") as fh:
                data = fh.read()
            info.size  = len(data)
            info.mtime = 0
            info.mode  = 0o644
            info.type  = tarfile.REGTYPE
            tf.addfile(info, io.BytesIO(data))

    return tmp.name


# ── extraction ─────────────────────────────────────────────────────────────────

def extract_layers(layer_digests: list[str], dest_dir: str, layer_path_fn):
    """
    Extract layers in order into dest_dir.
    Later layers overwrite earlier ones at the same path.

    Handles absolute symlinks (common in Linux base images like python:3.11-slim)
    which Python 3.14+ rejects with AbsoluteLinkError under the default filter.
    """
    for digest in layer_digests:
        tar_path = layer_path_fn(digest)
        if not os.path.exists(tar_path):
            raise FileNotFoundError(
                f"Layer {digest} not found on disk. "
                "The image may be broken (layer was deleted by rmi)."
            )
        with tarfile.open(tar_path, "r") as tf:
            for member in tf.getmembers():
                member.name = member.name.lstrip("/")
                if not member.name or ".." in member.name:
                    continue

                # Absolute symlinks: create manually to bypass Python security filter.
                # They resolve correctly once we chroot into dest_dir on Linux.
                if member.issym() and member.linkname.startswith("/"):
                    dest_path = os.path.join(dest_dir, member.name)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    if os.path.lexists(dest_path):
                        os.remove(dest_path)
                    os.symlink(member.linkname, dest_path)
                    continue

                # Skip hard links with absolute targets (rare)
                if member.islnk() and member.linkname.startswith("/"):
                    continue

                try:
                    tf.extract(member, path=dest_dir, set_attrs=False,
                               filter="fully_trusted")
                except TypeError:
                    # filter= param not available in Python < 3.12
                    tf.extract(member, path=dest_dir, set_attrs=False)


# ── internal helpers ───────────────────────────────────────────────────────────

def _glob_files(base_dir: str, pattern: str) -> list[str]:
    matched = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, base_dir)
            if _match_glob(rel_path, pattern):
                matched.append(rel_path)
    return matched


def _match_glob(rel_path: str, pattern: str) -> bool:
    if pattern == ".":
        return True
    return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
        rel_path, pattern.replace("**", "*")
    )


def _scan_dir(base_dir: str) -> dict[str, str]:
    """
    Return {rel_path: sha256_hex} for every regular (non-symlink) file
    under base_dir.

    Symlinks are skipped — dangling ones (pointing into a Linux rootfs)
    can't be read on Mac and don't need to be diffed anyway.
    """
    result = {}
    for root, dirs, files in os.walk(base_dir, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fname in sorted(files):
            abs_path = os.path.join(root, fname)
            if os.path.islink(abs_path):
                continue
            if not os.path.isfile(abs_path):
                continue
            rel_path = os.path.relpath(abs_path, base_dir)
            try:
                result[rel_path] = _sha256_file(abs_path)
            except (OSError, PermissionError):
                continue
    return result


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
