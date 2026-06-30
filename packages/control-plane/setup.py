from setuptools import find_packages, setup

RESOURCE_PACKAGES = ["pipelines", "schemas", "templates"]

setup(
    name="devframe-control-plane",
    version="0.1.0",
    packages=find_packages(include=["control_plane", "control_plane.*", *RESOURCE_PACKAGES]),
    package_data={
        "pipelines": ["*.yaml"],
        "schemas": [
            "*.json",
            "agent-runtime/*",
            "draft/*",
            "resource-integration/*",
        ],
        "templates": [
            "code_project/*",
            "context_handoff/*",
            "paper_iteration/*",
            "runtime-bootstrap/*",
            "visual_control_plane/*",
        ],
    },
    install_requires=["pyyaml>=6.0", "jsonschema>=4.0"],
    extras_require={"dev": ["pytest>=7.0", "hypothesis>=6.0"]},
    entry_points={
        "console_scripts": [
            "devframe=control_plane.cli:main",
            "rdgoal=control_plane.rdgoal_cli:main",
        ],
    },
    python_requires=">=3.10",
)
