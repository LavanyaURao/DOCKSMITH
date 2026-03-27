#!/usr/bin/env python3
"""
docksmith — A minimal Docker-like build and runtime system.

Commands:
  build   -t <name:tag> [--no-cache] <context>   Build an image
  images                                           List all images
  run     [-e KEY=VAL ...] <name:tag> [cmd ...]   Run a container
  rmi     <name:tag>                               Remove an image
  import  <tarball> <name:tag>                     Import a base image

Usage examples:
  docksmith build -t myapp:latest .
  docksmith images
  docksmith run myapp:latest
  docksmith run -e PORT=8080 myapp:latest
  docksmith rmi myapp:latest
  docksmith import alpine.tar alpine:3.18
"""

import argparse
import sys


def cmd_build(args):
    from docksmith.builder import build, BuildError
    from docksmith.parser import ParseError
    import os

    context = args.context
    tag = args.tag
    no_cache = args.no_cache

    if not os.path.isdir(context):
        print(f"Error: context directory '{context}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        build(context_dir=context, tag=tag, no_cache=no_cache)
    except (BuildError, ParseError, FileNotFoundError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nBuild failed: {e}", file=sys.stderr)
        raise


def cmd_images(args):
    from docksmith import store
    store.init_store()

    manifests = store.list_manifests()
    if not manifests:
        print("No images found.")
        return

    # Header
    fmt = "{:<20} {:<12} {:<14} {}"
    print(fmt.format("NAME", "TAG", "ID", "CREATED"))
    print("-" * 70)

    for m in sorted(manifests, key=lambda x: x.get("created", "")):
        name    = m.get("name", "")
        tag     = m.get("tag", "")
        digest  = m.get("digest", "")
        short_id = digest.replace("sha256:", "")[:12]
        created = m.get("created", "")[:19].replace("T", " ")  # readable datetime
        print(fmt.format(name, tag, short_id, created))


def cmd_run(args):
    from docksmith.runtime import run_container

    name, tag = _parse_tag(args.image)

    # Parse -e KEY=VALUE overrides
    extra_env = {}
    for kv in (args.env or []):
        if "=" not in kv:
            print(f"Error: -e flag must be KEY=VALUE, got: '{kv}'", file=sys.stderr)
            sys.exit(1)
        k, _, v = kv.partition("=")
        extra_env[k] = v

    cmd_override = args.cmd if args.cmd else None

    try:
        exit_code = run_container(
            name=name,
            tag=tag,
            cmd_override=cmd_override,
            extra_env=extra_env,
        )
        sys.exit(exit_code)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_rmi(args):
    from docksmith import store
    store.init_store()

    name, tag = _parse_tag(args.image)
    try:
        deleted = store.delete_manifest(name, tag)
        print(f"Removed {name}:{tag}")
        if deleted:
            print(f"Deleted {len(deleted)} layer file(s).")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_import(args):
    from docksmith.importer import import_image
    import os

    tarball = args.tarball
    tag = args.tag

    if not os.path.exists(tarball):
        print(f"Error: tarball '{tarball}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        import_image(tarball_path=tarball, tag=tag)
    except Exception as e:
        print(f"Error importing image: {e}", file=sys.stderr)
        sys.exit(1)


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_tag(tag_str: str) -> tuple[str, str]:
    if ":" in tag_str:
        name, t = tag_str.split(":", 1)
        return name, t
    return tag_str, "latest"


# ── argument parser ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="docksmith",
        description="A minimal Docker-like build and runtime system.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    # build
    p_build = subparsers.add_parser("build", help="Build an image from a Docksmithfile")
    p_build.add_argument("-t", dest="tag", required=True, metavar="name:tag",
                         help="Name and tag for the image")
    p_build.add_argument("--no-cache", action="store_true",
                         help="Skip all cache lookups and writes")
    p_build.add_argument("context", metavar="<context>",
                         help="Build context directory (must contain Docksmithfile)")
    p_build.set_defaults(func=cmd_build)

    # images
    p_images = subparsers.add_parser("images", help="List all images")
    p_images.set_defaults(func=cmd_images)

    # run
    p_run = subparsers.add_parser("run", help="Run a container")
    p_run.add_argument("-e", dest="env", action="append", metavar="KEY=VALUE",
                       help="Set environment variable (repeatable)")
    p_run.add_argument("image", metavar="<name:tag>", help="Image to run")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, metavar="[cmd ...]",
                       help="Command override")
    p_run.set_defaults(func=cmd_run)

    # rmi
    p_rmi = subparsers.add_parser("rmi", help="Remove an image")
    p_rmi.add_argument("image", metavar="<name:tag>")
    p_rmi.set_defaults(func=cmd_rmi)

    # import
    p_import = subparsers.add_parser("import", help="Import a base image from a Docker tarball")
    p_import.add_argument("tarball", metavar="<tarball>", help="Path to .tar file (from docker save)")
    p_import.add_argument("tag", metavar="<name:tag>", help="Name and tag to assign")
    p_import.set_defaults(func=cmd_import)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()
