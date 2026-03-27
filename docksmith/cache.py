"""
cache.py — Deterministic cache-key computation.

Cache key inputs (per spec):
  1. Digest of the previous layer (or base image manifest digest for the first
     layer-producing instruction).
  2. Full instruction text as written in the Docksmithfile.
  3. Current WORKDIR value (empty string if not set).
  4. Current ENV state: all key=value pairs in lexicographically sorted key order
     (empty string if none set).
  5. COPY only: SHA-256 of each source file's raw bytes, concatenated in
     lexicographically sorted path order.
"""

import hashlib
import json


def compute_cache_key(
    prev_digest: str,
    instruction_text: str,
    workdir: str,
    env: dict[str, str],
    file_hashes: dict[str, str] | None = None,
) -> str:
    """
    Returns a hex SHA-256 cache key string.

    Args:
        prev_digest:      digest of the last layer (or base manifest digest).
        instruction_text: full raw instruction line from the Docksmithfile.
        workdir:          current WORKDIR value, or "" if not set.
        env:              accumulated ENV dict at this point in the build.
        file_hashes:      {rel_path: sha256_hex} for COPY; None for RUN.
    """
    parts: list[str] = []

    # 1. Previous layer digest
    parts.append(prev_digest)

    # 2. Instruction text (full raw line)
    parts.append(instruction_text)

    # 3. Current WORKDIR
    parts.append(workdir or "")

    # 4. ENV state — sorted by key
    if env:
        sorted_env = sorted(env.items())           # lexicographic by key
        parts.append(json.dumps(sorted_env, separators=(",", ":")))
    else:
        parts.append("")

    # 5. COPY file hashes — sorted by path
    if file_hashes:
        sorted_hashes = [file_hashes[k] for k in sorted(file_hashes.keys())]
        parts.append("".join(sorted_hashes))
    else:
        parts.append("")

    combined = "\n".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()
