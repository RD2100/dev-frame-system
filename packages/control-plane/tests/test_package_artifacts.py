from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import venv
import zipfile


CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_SCHEMAS = REPO_ROOT / "schemas"


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _run(*args: str | Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_wheel_and_sdist_ship_public_schemas_for_clean_install(
    tmp_path: Path,
    request,
) -> None:
    egg_info = CONTROL_PLANE_ROOT / "devframe_control_plane.egg-info"
    assert not egg_info.exists()
    request.addfinalizer(lambda: shutil.rmtree(egg_info, ignore_errors=True))

    expected = {
        path.relative_to(PUBLIC_SCHEMAS).as_posix(): path.read_bytes()
        for path in PUBLIC_SCHEMAS.rglob("*.schema.json")
    }
    assert "external_review_bundle.schema.json" in expected

    build_env = tmp_path / "build-env"
    venv.EnvBuilder(with_pip=True).create(build_env)
    build_python = _venv_python(build_env)
    _run(build_python, "-m", "pip", "install", "build", cwd=tmp_path)

    dist = tmp_path / "dist"
    _run(
        build_python,
        "-m",
        "build",
        "--outdir",
        dist,
        CONTROL_PLANE_ROOT,
        cwd=tmp_path,
    )
    wheel = next(dist.glob("*.whl"))
    sdist = next(dist.glob("*.tar.gz"))

    with zipfile.ZipFile(wheel) as archive:
        wheel_schemas = {
            name.removeprefix("schemas/"): archive.read(name)
            for name in archive.namelist()
            if name.startswith("schemas/") and name.endswith(".schema.json")
        }
    assert wheel_schemas == expected

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_schemas = {
            name.split("/schemas/", 1)[1]: archive.extractfile(name).read()
            for name in archive.getnames()
            if "/schemas/" in name and name.endswith(".schema.json")
        }
    assert sdist_schemas == expected

    expected_hash = hashlib.sha256(
        expected["external_review_bundle.schema.json"]
    ).hexdigest()
    for label, artifact in (("wheel", wheel), ("sdist", sdist)):
        install_env = tmp_path / f"{label}-install-env"
        venv.EnvBuilder(with_pip=True).create(install_env)
        install_python = _venv_python(install_env)
        _run(install_python, "-m", "pip", "install", artifact, cwd=tmp_path)
        probe = _run(
            install_python,
            "-I",
            "-c",
            (
                "import json; "
                "import hashlib; "
                "from pathlib import Path; "
                "import sys; "
                "import control_plane; "
                "from jsonschema import Draft7Validator; "
                "root = Path(control_plane.__file__).resolve().parent.parent; "
                "schema_path = root / 'schemas' / 'external_review_bundle.schema.json'; "
                "schema_bytes = schema_path.read_bytes(); "
                "assert hashlib.sha256(schema_bytes).hexdigest() == sys.argv[1]; "
                "schema = json.loads(schema_bytes); "
                "Draft7Validator.check_schema(schema); "
                "assert 'site-packages' in schema_path.as_posix(); "
                "print(schema_path)"
            ),
            expected_hash,
            cwd=tmp_path,
        )
        assert "site-packages" in probe.stdout.replace("\\", "/")
