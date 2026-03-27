#!/usr/bin/env python3
"""
Sample Docksmith app.

Prints a greeting using the APP_NAME environment variable,
lists files in /app, and shows the working directory.
Demonstrates ENV override via -e at runtime.
"""

import os

app_name = os.environ.get("APP_NAME", "World")
version  = os.environ.get("VERSION", "unknown")

print("=" * 40)
print(f"  Docksmith Sample App")
print(f"  Hello, {app_name}!")
print(f"  Version: {version}")
print(f"  Working dir: {os.getcwd()}")
print("=" * 40)

print("\nFiles in /app:")
try:
    for f in sorted(os.listdir("/app")):
        print(f"  {f}")
except Exception as e:
    print(f"  (could not list: {e})")

# Write a file inside the container to prove isolation
test_file = "/tmp/container_test.txt"
with open(test_file, "w") as f:
    f.write("This file exists only inside the container.\n")
print(f"\nWrote '{test_file}' inside container.")
print("(This file must NOT appear on the host — check after run!)")
# changed
# changed
# changed
