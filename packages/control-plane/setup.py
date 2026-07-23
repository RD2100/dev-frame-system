from pathlib import Path
import shutil

from setuptools import find_packages, setup
from setuptools.command.sdist import sdist as _sdist

SETUP_ROOT = Path(__file__).resolve().parent
REPO_SCHEMAS = SETUP_ROOT.parents[1] / "schemas"
SDIST_SCHEMAS = SETUP_ROOT / "schemas"
PUBLIC_SCHEMAS = SDIST_SCHEMAS if SDIST_SCHEMAS.is_dir() else REPO_SCHEMAS
RESOURCE_PACKAGES = ["pipelines", "templates"]


class SdistWithPublicSchemas(_sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        for source in PUBLIC_SCHEMAS.rglob("*.schema.json"):
            target = Path(base_dir) / "schemas" / source.relative_to(PUBLIC_SCHEMAS)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


setup(
    name="devframe-control-plane",
    version="0.1.0",
    packages=find_packages(include=["control_plane", "control_plane.*", *RESOURCE_PACKAGES])
    + ["schemas"],
    package_dir={"schemas": str(PUBLIC_SCHEMAS)},
    cmdclass={"sdist": SdistWithPublicSchemas},
    package_data={
        "control_plane": ["*.schema.json"],
        "pipelines": ["*.yaml"],
        "schemas": ["**/*.schema.json"],
        "templates": [
            "code_project/*",
            "context_handoff/*",
            "paper_iteration/*",
            "runtime-bootstrap/*",
            "visual_control_plane/*",
        ],
    },
    install_requires=["pyyaml>=6.0", "jsonschema>=4.0"],
    extras_require={"dev": ["pytest>=7.0", "hypothesis>=6.0", "playwright>=1.40.0", "wheel>=0.40.0"]},
    entry_points={
        "console_scripts": [
            "devframe=control_plane.cli:main",
            "rdgoal=control_plane.rdgoal_cli:main",
        ],
    },
    python_requires=">=3.10",
)
