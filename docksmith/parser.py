"""
parser.py — Parse a Docksmithfile into a list of instruction dicts.

Supported instructions: FROM, COPY, RUN, WORKDIR, ENV, CMD
Any unrecognised instruction raises a ParseError with the line number.
"""

import json
import re

VALID_INSTRUCTIONS = {"FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"}


class ParseError(Exception):
    pass


def parse_docksmithfile(path: str) -> list[dict]:
    """
    Returns a list of instruction dicts, e.g.:
      {"instruction": "FROM",    "args": "alpine:3.18",     "line": 1}
      {"instruction": "COPY",    "args": ". /app",          "line": 2}
      {"instruction": "RUN",     "args": "echo hello",      "line": 3}
      {"instruction": "WORKDIR", "args": "/app",            "line": 4}
      {"instruction": "ENV",     "args": "KEY=value",       "line": 5}
      {"instruction": "CMD",     "args": '["python","main.py"]', "line": 6}
    """
    with open(path) as f:
        lines = f.readlines()

    instructions = []
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        lineno = i + 1

        # Handle line continuation
        while raw.endswith("\\"):
            raw = raw[:-1]
            i += 1
            if i < len(lines):
                raw += " " + lines[i].strip().rstrip("\n")

        line = raw.strip()
        i += 1

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        # Split into keyword + rest
        parts = line.split(None, 1)
        keyword = parts[0].upper()
        args = parts[1].strip() if len(parts) > 1 else ""

        if keyword not in VALID_INSTRUCTIONS:
            raise ParseError(
                f"Line {lineno}: unrecognised instruction '{parts[0]}'. "
                f"Valid instructions are: {', '.join(sorted(VALID_INSTRUCTIONS))}"
            )

        instructions.append({
            "instruction": keyword,
            "args": args,
            "line": lineno,
            "raw": line,
        })

    return instructions


def parse_from(args: str) -> tuple[str, str]:
    """Parse 'image:tag' or 'image' → (name, tag). Default tag = 'latest'."""
    if ":" in args:
        name, tag = args.split(":", 1)
    else:
        name, tag = args, "latest"
    return name.strip(), tag.strip()


def parse_copy(args: str) -> tuple[str, str]:
    """Parse 'src dest' → (src, dest). Both are stripped."""
    parts = args.split(None, 1)
    if len(parts) != 2:
        raise ParseError(f"COPY requires <src> <dest>, got: '{args}'")
    return parts[0].strip(), parts[1].strip()


def parse_env(args: str) -> tuple[str, str]:
    """Parse 'KEY=value' → (key, value)."""
    if "=" not in args:
        raise ParseError(f"ENV requires KEY=value format, got: '{args}'")
    key, _, value = args.partition("=")
    return key.strip(), value.strip()


def parse_cmd(args: str) -> list[str]:
    """Parse CMD JSON array, e.g. '["python", "main.py"]' → ['python', 'main.py']."""
    try:
        cmd = json.loads(args)
        if not isinstance(cmd, list):
            raise ParseError(f"CMD must be a JSON array, got: '{args}'")
        return [str(x) for x in cmd]
    except json.JSONDecodeError as e:
        raise ParseError(f"CMD is not valid JSON: '{args}' — {e}")
