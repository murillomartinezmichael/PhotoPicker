"""Install and exercise both built distributions in fresh core-only environments.

Run after python -m build in the approved CI environment. This installs packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def consumer():
    import importlib.util

    from PIL import Image

    import photopicker
    from photopicker.classifier import StubClassifier
    from photopicker.core import pick_photos

    installed = Path(photopicker.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), installed
    for optional in ("torch", "transformers", "mediapipe", "anthropic"):
        assert importlib.util.find_spec(optional) is None, optional
    source = Path("synthetic")
    source.mkdir()
    photo = source / "checker.png"
    image = Image.new("RGB", (256, 256))
    image.putdata([
        (255, 255, 255) if (x // 8 + y // 8) % 2 else (0, 0, 0)
        for y in range(256) for x in range(256)
    ])
    image.save(photo)
    before = hashlib.sha256(photo.read_bytes()).hexdigest()
    result = pick_photos(source, "default", classifier=StubClassifier())
    manifest = result.to_manifest()
    assert len(manifest["picks"]) == 1, manifest
    assert manifest["picks"][0]["filename"] == photo.name
    assert manifest["picks"][0]["dimensions"] == {"width": 256, "height": 256}
    assert hashlib.sha256(photo.read_bytes()).hexdigest() == before
    print(json.dumps({"installed": str(installed), "synthetic_picks": 1,
                      "optional_models_absent": True, "source_unchanged": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", action="store_true")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if args.consumer:
        consumer()
        return
    artifacts = [*args.dist.glob("*.whl"), *args.dist.glob("*.tar.gz")]
    assert len(artifacts) == 2, "Expected exactly one wheel and one sdist"
    assert sum(p.suffix == ".whl" for p in artifacts) == 1
    script = Path(__file__).resolve()
    for artifact in artifacts:
        with tempfile.TemporaryDirectory(prefix="photopicker-consumer-") as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            executables = environment / ("Scripts" if os.name == "nt" else "bin")
            python = executables / ("python.exe" if os.name == "nt" else "python")
            subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install",
                            "--no-cache-dir", str(artifact.resolve())], cwd=root,
                           check=True, timeout=300)
            subprocess.run([str(python), "-I", "-m", "pip", "check"], cwd=root,
                           check=True, timeout=30)
            for command in ("photopicker", "photopicker-cull"):
                executable = executables / (command + (".exe" if os.name == "nt" else ""))
                subprocess.run([str(executable), "--help"], cwd=root,
                               check=True, timeout=30)
            subprocess.run([str(python), "-I", str(script), "--consumer"], cwd=root,
                           check=True, timeout=60)
            print(f"PASS {artifact.name} sha256={hashlib.sha256(artifact.read_bytes()).hexdigest()}",
                  flush=True)


if __name__ == "__main__":
    main()
