from setuptools import setup, find_packages

setup(
    name="docksmith",
    version="1.0.0",
    description="A minimal Docker-like build and runtime system built from scratch",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "docksmith=docksmith.cli:main",
        ],
    },
)
