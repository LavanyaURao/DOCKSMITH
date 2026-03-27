# Docksmith

A minimal Docker-like build and runtime system built from scratch.

---

## What It Does

Docksmith implements three things:

1. **Build system** — reads a `Docksmithfile`, executes 6 instructions (`FROM`, `COPY`, `RUN`, `WORKDIR`, `ENV`, `CMD`), produces content-addressed layer tars and a JSON manifest.
2. **Build cache** — deterministic SHA-256 cache keys, `[CACHE HIT]`/`[CACHE MISS]` reporting, cascade invalidation.
3. **Container runtime** — extracts layers into a temp directory, isolates the process using `unshare` + `chroot`, runs the command, cleans up.

---

## Project Structure

```
docksmith/
├── docksmith/
│   ├── __init__.py
│   ├── cli.py          ← entry point (all CLI commands)
│   ├── builder.py      ← build engine (orchestrates everything)
│   ├── parser.py       ← Docksmithfile parser
│   ├── layers.py       ← tar layer creation and extraction
│   ├── cache.py        ← cache key computation
│   ├── isolation.py    ← OS-level process isolation (unshare + chroot)
│   ├── runtime.py      ← container runtime (docksmith run)
│   ├── importer.py     ← base image import (one-time setup)
│   └── store.py        ← disk I/O for ~/.docksmith/
├── sample_app/
│   ├── Docksmithfile   ← uses all 6 instructions
│   └── app.py          ← sample Python app
├── setup.py
├── setup.sh            ← one-time base image import
└── demo.sh             ← runs all 8 demo scenarios
```

---

## Local Store Layout

```
~/.docksmith/
  images/          # one JSON manifest per image
  layers/          # content-addressed tar files named sha256_<hex>.tar
  cache/
    cache_index.json  # cache key → layer digest mapping
```

---

## Installation

```bash
# Install docksmith CLI
pip install -e .

# Or install without pip
python3 setup.py develop
```

---

## Initial Setup (One-Time)

Base images must be downloaded ONCE and imported into the local store.
After this, everything works completely offline.

```bash
# Option A: Use the setup script (requires Docker once)
bash setup.sh

# Option B: Manual import
docker pull python:3.11-slim
docker save python:3.11-slim -o /tmp/python311slim.tar
sudo docksmith import /tmp/python311slim.tar python:3.11-slim
```

---

## CLI Reference

### `docksmith build`
```bash
docksmith build -t <name:tag> [--no-cache] <context>

# Examples
sudo docksmith build -t myapp:latest .
sudo docksmith build -t myapp:latest --no-cache .
```
- Parses `Docksmithfile` in `<context>`
- Each `COPY`/`RUN` step prints cache status and duration
- `FROM` steps print without cache status (not a layer-producing step)

### `docksmith images`
```bash
docksmith images
```
Lists all images: Name, Tag, ID (first 12 chars of digest), Created.

### `docksmith run`
```bash
docksmith run [-e KEY=VALUE ...] <name:tag> [cmd ...]

# Examples
sudo docksmith run myapp:latest
sudo docksmith run -e APP_NAME=Alice myapp:latest
sudo docksmith run myapp:latest echo "hello from container"
```
- Assembles filesystem, runs command in isolation, waits for exit, prints exit code.
- `-e` overrides image ENV values. Repeatable.

### `docksmith rmi`
```bash
docksmith rmi <name:tag>

# Example
docksmith rmi myapp:latest
```
Removes the manifest and all associated layer files.

### `docksmith import`
```bash
docksmith import <tarball.tar> <name:tag>

# Example
docksmith import /tmp/alpine.tar alpine:3.18
```
One-time setup command. Imports a Docker-format tarball into the local store.

---

## Requirements

- **Python 3.11+**
- **Linux** (isolation uses `unshare` + `chroot`)
- **Root** (`sudo`) for `build` and `run` (required for `chroot`/`unshare`)
- No Docker, runc, or any container tool used during build/run
- All operations work fully offline after initial setup

---

# Docksmith Setup & Demo Guide

This guide walks you through setting up and running the Docksmith project from scratch.

---

## Prerequisites

- macOS (host machine)
- Docker installed
- Python 3.10+

---

# Setup Instructions

## Step 1 — Setup project (Mac Terminal)

```bash
cd docksmith
python3 -m venv venv
source venv/bin/activate
sed -i '' 's/>=3.11/>=3.10/' setup.py
pip3 install -e .
```

---

## Step 2 — Import base image (one-time setup)

```bash
bash setup.sh
```

---

## Step 3 — Save base image tar

```bash
docker save python:3.11-slim -o /tmp/python311slim.tar
```

---

## Step 4 — Start Linux container

```bash
docker run -it --rm --privileged \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  -v $(pwd):/project \
  -v ~/.docksmith:/root/.docksmith \
  -v /tmp/python311slim.tar:/tmp/python311slim.tar \
  ubuntu:22.04 bash
```

---

# Inside the Container

## Step 5 — Install dependencies

```bash
cd /project
apt-get update -qq && apt-get install -y python3 python3-pip -qq
sed -i 's/>=3.11/>=3.10/' setup.py && pip3 install -e . -q && echo "DONE"
```

---

## Step 6 — Import base image into Docksmith

```bash
docksmith import /tmp/python311slim.tar python:3.11-slim
```

---

# Demo Commands

## Demo 1 — Cold Build (No Cache)

```bash
docksmith build -t myapp:latest sample_app/ --no-cache
```

---

## Demo 2 — Warm Build (Cache Hit)

```bash
docksmith build -t myapp:latest sample_app/
```

---

## Demo 3 — Partial Rebuild

```bash
echo "# changed" >> sample_app/app.py
docksmith build -t myapp:latest sample_app/
```

---

## Demo 4 — List Images

```bash
docksmith images
```

---

## Demo 5 — Run Container

```bash
docksmith run myapp:latest
```

---

## Demo 6 — Environment Variable Override

```bash
docksmith run -e APP_NAME=Lavanya -e VERSION=2.0.0 myapp:latest
```

---

## Demo 7 — Isolation Check

```bash
ls /tmp/container_test.txt
```

**Expected Output:**
```
No such file or directory
```

---

## 🗑️ Demo 8 — Remove Image

```bash
docksmith rmi myapp:latest
docksmith images
```

---

#  Important Notes

- Steps 1–4 must be run on your **terminal**
- Steps 5 onward must be run **inside the Docker container**
- Do NOT run:
  ```bash
  docksmith rmi python:3.11-slim
  ```
  This will break the base image

- Every time you start a new container:
  - Repeat **Step 5 and Step 6**

---
