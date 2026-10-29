from setuptools import setup, find_packages

setup(
    name="devframe-control-plane",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pyyaml>=6.0"],
    extras_require={"dev": ["pytest>=7.0"]},
    entry_points={
        "console_scripts": [
            "devframe=control_plane.cli:main",
        ],
    },
    python_requires=">=3.10",
)
