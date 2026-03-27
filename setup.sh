#!/bin/bash
# setup.sh — One-time setup: pull base image and import into local store.
# Run this ONCE before any builds. After this, everything works offline.

set -e

echo "=== Docksmith Initial Setup ==="
echo ""

# Check if Docker is available for the one-time pull
if ! command -v docker &>/dev/null; then
    echo "Docker is required ONCE for the initial base image download."
    echo "After this setup, docksmith works completely offline."
    echo ""
    echo "Please install Docker, run this script once, then Docker is no longer needed."
    exit 1
fi

echo "Step 1: Pulling python:3.11-slim base image via Docker (one-time only)..."
docker pull python:3.11-slim

echo ""
echo "Step 2: Saving to tarball..."
docker save python:3.11-slim -o /tmp/python311slim.tar

echo ""
echo "Step 3: Importing into ~/.docksmith/ store..."
python3 -m docksmith.cli import /tmp/python311slim.tar python:3.11-slim

echo ""
echo "Step 4: Cleaning up tarball..."
rm -f /tmp/python311slim.tar

echo ""
echo "=== Setup complete! ==="
echo ""
echo "You can now build offline:"
echo "  cd sample_app"
echo "  sudo docksmith build -t myapp:latest ."
echo "  sudo docksmith run myapp:latest"
echo ""
echo "Note: docksmith run requires root (for chroot/unshare isolation)."
