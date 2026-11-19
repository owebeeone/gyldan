"""Plan the release matrix and verify that it produced exactly one wheel per row."""

import argparse
import hashlib
import itertools
import json
import os
import re
from pathlib import Path

PYTHONS = ("3.12", "3.13", "3.14", "3.15")
PLATFORMS = (
    {
        "target": "linux-amd64",
        "runner": "ubuntu-24.04",
        "arch": "x64",
        "platform": "manylinux_2_34_x86_64",
        "container": "quay.io/pypa/manylinux_2_34_x86_64@sha256:eaf34dc7cfdff5db7109a92c87b4f797b8bbd1f9ed8da48c02c4025b6ea76650",
    },
    {
        "target": "raspberry-pi-arm64",
        "runner": "ubuntu-24.04-arm",
        "arch": "arm64",
        "platform": "manylinux_2_34_aarch64",
        "container": "quay.io/pypa/manylinux_2_34_aarch64@sha256:f87b0720c0cd324fb712d229700c6ca6a5f3248de5828cd3d0e87b32c29f9abb",
    },
    {
        "target": "windows-amd64",
        "runner": "windows-2025-vs2026",
        "arch": "x64",
        "platform": "win_amd64",
        "container": "",
    },
    {
        "target": "macos-amd64",
        "runner": "macos-26-intel",
        "arch": "x64",
        "platform": "macosx_26_0_x86_64",
        "container": "",
    },
    {
        "target": "macos-arm64",
        "runner": "macos-26",
        "arch": "arm64",
        "platform": "macosx_26_0_arm64",
        "container": "",
    },
)


def release_version(value):
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?",
        value,
    ):
        raise argparse.ArgumentTypeError("Use a canonical version such as 0.0.0a1")
    return value


def builds():
    for platform, python in itertools.product(PLATFORMS, PYTHONS):
        abi = "cp" + python.replace(".", "")
        yield dict(
            platform, python=python, abi=abi, tag=f"{abi}-{abi}-{platform['platform']}"
        )


def plan(version):
    outputs = {
        "version": version,
        "prerelease": str(bool(re.search(r"[a-z]", version))).lower(),
        "matrix": json.dumps({"include": list(builds())}, separators=(",", ":")),
    }
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        for name, value in outputs.items():
            print(f"{name}={value}", file=stream)
    print(f"Planned {len(list(builds()))} wheel builds for Gyldan {version}")


def verify(version, directory, checksums):
    expected = {f"gyldan-{version}-{build['tag']}.whl" for build in builds()}
    wheels = {file.name: file for file in directory.glob("*.whl") if file.is_file()}
    if wheels.keys() != expected:
        raise SystemExit(
            f"Missing wheels: {sorted(expected - wheels.keys())}; unexpected: {sorted(wheels.keys() - expected)}"
        )
    with checksums.open("w", encoding="ascii", newline="\n") as stream:
        for name, wheel in sorted(wheels.items()):
            print(
                f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {name}", file=stream
            )
    print(f"Verified all {len(wheels)} wheel filenames and wrote checksums")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", type=release_version)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--checksums", type=Path, default=Path("SHA256SUMS"))
    args = parser.parse_args()
    if args.dist is None:
        plan(args.version)
    else:
        verify(args.version, args.dist, args.checksums)
