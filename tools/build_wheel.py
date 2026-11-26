"""Build, assemble and qualify one Gyldan wheel from pinned component sources."""

import argparse
import os
import subprocess
import sys
from configparser import ConfigParser
from email.message import EmailMessage
from email.parser import BytesParser
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from release_matrix import release_version
from wheel.wheelfile import WheelFile

COMPONENTS = {
    "gyldan-core-py": "gyldan_core",
    "gyldan-python": "gyldan",
    "gyldan-shared-py": "gyldan_shared",
    "gyldan-validator": "gyldan_validator",
}
TOOLS = Path(__file__).resolve().parent


def run(label, args, env=None):
    print(label, flush=True)
    # A failed compiler invocation can print excerpts from private source.
    result = subprocess.run(args, env=env, capture_output=True, check=False)
    if result.returncode:
        if not os.environ.get("GITHUB_ACTIONS"):
            sys.stderr.buffer.write(result.stdout + result.stderr)
        elif label == "Run the Shared Python suite":
            # Name the failing tests and give the totals. The test identifiers
            # are printed alone: an assertion message can quote private source.
            lines = result.stdout.decode(errors="replace").strip().splitlines()
            for line in lines:
                if line.startswith(("FAILED ", "ERROR ")):
                    print(line.split(" - ", 1)[0], flush=True)
            if lines:
                print(lines[-1], flush=True)
        raise SystemExit(f"{label} failed with exit status {result.returncode}")
    if label == "Run the Shared Python suite":
        print(
            result.stdout.decode(errors="replace").strip().splitlines()[-1], flush=True
        )


def build_components(sources, destination, env):
    for name in COMPONENTS:
        options = []
        if name == "gyldan-shared-py":
            options = [
                f"-Ccmake.define.GYLDAN_DEPENDENCY_ROOT={sources}",
                f"-Ccmake.define.Python3_EXECUTABLE={sys.executable}",
                "-Ccmake.define.GYLDAN_SHARED_PY_BUILD_TESTS=OFF",
            ]
        run(
            f"Build {name}",
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(destination),
                *options,
                str(sources / name),
            ],
            env,
        )


def assemble(version, tag, components, output):
    files = {}
    for path in components.glob("*.whl"):
        name, component_version, build_tag, tags = parse_wheel_filename(path.name)
        if name not in COMPONENTS or name in files or build_tag or len(tags) != 1:
            raise ValueError(f"Unexpected component wheel {path.name}")
        expected = (
            "py3-none-any" if name in ("gyldan-core-py", "gyldan-python") else tag
        )
        if str(next(iter(tags))) != expected:
            raise ValueError(f"Expected {expected} for {path.name}")
        files[name] = path, component_version
    if files.keys() != COMPONENTS.keys():
        raise ValueError("The four Gyldan component wheels are required")

    metadata = EmailMessage()
    metadata["Metadata-Version"] = "2.4"
    metadata["Name"] = "gyldan"
    metadata["Version"] = version
    metadata["Summary"] = "GyldanDB Python API and native file-backed database provider"
    metadata["Description-Content-Type"] = "text/markdown"
    metadata["Requires-Python"] = ">=3.12"
    metadata["Project-URL"] = "Source, https://github.com/owebeeone/gyldan"
    metadata["Project-URL"] = "Documentation, https://owebeeone.github.io/gyldan/"
    metadata["License-Expression"] = (
        "GPL-3.0-only AND BSD-3-Clause AND MIT AND Unicode-3.0"
    )
    info = f"gyldan-{version}.dist-info"
    dependencies, payload = set(), {}
    for name in ("LICENSE", "COPYRIGHT"):
        metadata["License-File"] = name
        payload[f"{info}/licenses/{name}"] = (TOOLS.parent / name).read_bytes()
    entry_points = ConfigParser()
    entry_points.optionxform = str
    for name, (path, _) in sorted(files.items()):
        with WheelFile(path) as wheel:
            original_info = wheel.dist_info_path
            original = BytesParser().parsebytes(wheel.read(f"{original_info}/METADATA"))
            for raw in original.get_all("Requires-Dist", []):
                dependency = Requirement(raw)
                if dependency.marker and "extra" in str(dependency.marker):
                    continue
                bundled = files.get(canonicalize_name(dependency.name))
                if bundled is None:
                    dependencies.add(str(dependency))
                elif bundled[1] not in dependency.specifier:
                    raise ValueError(
                        f"Incompatible bundled dependency of {name}: {raw}"
                    )
            for member in wheel.namelist():
                if member.endswith("/"):
                    continue
                if member == f"{original_info}/entry_points.txt":
                    entry_points.read_string(wheel.read(member).decode("utf-8"), name)
                elif member.startswith(f"{original_info}/licenses/"):
                    license_name = f"{name}/{member.split('/licenses/', 1)[1]}"
                    metadata["License-File"] = license_name
                    payload[f"{info}/licenses/{license_name}"] = wheel.read(member)
                elif not member.startswith(f"{original_info}/"):
                    if (
                        not member.startswith(COMPONENTS[name] + "/")
                        or member in payload
                    ):
                        raise ValueError(
                            f"Unexpected or duplicate payload path {member}"
                        )
                    payload[member] = wheel.read(member)
    for dependency in sorted(dependencies):
        metadata["Requires-Dist"] = dependency
    metadata.set_payload((TOOLS.parent / "README.md").read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    result = output / f"gyldan-{version}-{tag}.whl"
    with WheelFile(result, "w") as wheel:
        for name, contents in sorted(payload.items()):
            wheel.writestr(name, contents)
        wheel.writestr(f"{info}/METADATA", metadata.as_bytes())
        wheel.writestr(
            f"{info}/WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n"
        )
        with StringIO() as stream:
            entry_points.write(stream, space_around_delimiters=False)
            wheel.writestr(f"{info}/entry_points.txt", stream.getvalue())
    return result


def qualify(version, wheel, sources, directory, env):
    build = directory / "fixture"
    run(
        "Configure the Shared integration fixture",
        [
            "cmake",
            "-S",
            str(sources / "gyldan-shared-py"),
            "-B",
            str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DGYLDAN_SHARED_PY_BUILD_TESTS=ON",
            f"-DGYLDAN_DEPENDENCY_ROOT={sources}",
            f"-DPython3_EXECUTABLE={sys.executable}",
        ],
        env,
    )
    run(
        "Build the Shared integration fixture",
        [
            "cmake",
            "--build",
            str(build),
            "--config",
            "Release",
            "--target",
            "shared_py_fixture",
        ],
        env,
    )
    fixture_name = "shared_py_fixture.exe" if os.name == "nt" else "shared_py_fixture"
    fixture = next(
        path
        for path in (build / fixture_name, build / "Release" / fixture_name)
        if path.is_file()
    )
    virtualenv = directory / "env"
    run(
        "Create a clean test environment",
        [sys.executable, "-m", "venv", str(virtualenv)],
        env,
    )
    python = virtualenv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        "Install the consolidated wheel",
        [str(python), "-m", "pip", "install", str(wheel), "pytest>=8,<10"],
        env,
    )
    run("Check installed dependencies", [str(python), "-m", "pip", "check"], env)
    run(
        "Smoke-test the installed Gyldan package",
        [str(python), "-I", str(TOOLS / "smoke.py"), version],
        env,
    )
    # The suite compares the native provider with the in-memory Reference
    # provider, which is a test package and is not part of the wheel. It is
    # installed after the smoke test, which requires gyldan to be the only
    # installed Gyldan distribution.
    run(
        "Install the Reference test provider",
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(sources / "gyldan-test-py"),
        ],
        env,
    )
    tests = sources / "gyldan-shared-py/tests"
    run(
        "Run the Shared Python suite",
        [
            str(python),
            "-m",
            "pytest",
            "-q",
            "-rfE",
            "--import-mode=importlib",
            "-p",
            "no:cacheprovider",
            str(tests),
        ],
        # Some test modules import helpers from a sibling test module.
        dict(env, GYLDAN_SHARED_PY_FIXTURE=str(fixture), PYTHONPATH=str(tests)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", type=release_version, required=True)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument(
        "--tag", required=True, help="The final expected Python-ABI-platform tag"
    )
    args = parser.parse_args()
    sources, dist = args.sources.resolve(), args.dist.resolve()
    env = dict(
        os.environ,
        CMAKE_BUILD_PARALLEL_LEVEL="2",
        ASTICHI_LOWER_ENGINE="python",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for name in ("GYLDAN_ENABLE_LOGS", "PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    native_platform = args.tag.rsplit("-", 1)[1]
    linux = native_platform.startswith("manylinux_")
    build_tag = args.tag.replace("manylinux_2_34_", "linux_") if linux else args.tag
    if build_tag not in {str(tag) for tag in sys_tags()}:
        raise SystemExit(f"The active interpreter cannot build {build_tag}")
    if native_platform.startswith("macosx_"):
        env["MACOSX_DEPLOYMENT_TARGET"] = "26.0"
    if os.name == "nt":
        env.setdefault("CMAKE_GENERATOR", "Visual Studio 17 2022")
        env.setdefault("CMAKE_GENERATOR_PLATFORM", "x64")
    with TemporaryDirectory(prefix="gyldan-wheel-") as temporary:
        work = Path(temporary)
        components = work / "components"
        build_components(sources, components, env)
        wheel = assemble(args.version, build_tag, components, work / "assembled")
        if linux:
            run(
                "Repair the Linux wheel for manylinux",
                [
                    "auditwheel",
                    "repair",
                    "--only-plat",
                    "--plat",
                    native_platform,
                    "--wheel-dir",
                    str(work / "repaired"),
                    str(wheel),
                ],
                env,
            )
            wheel = work / "repaired" / f"gyldan-{args.version}-{args.tag}.whl"
        if not wheel.is_file() or wheel.name != f"gyldan-{args.version}-{args.tag}.whl":
            raise SystemExit("The build did not produce the expected wheel tag")
        qualify(args.version, wheel, sources, work, env)
        dist.mkdir(parents=True, exist_ok=True)
        (dist / wheel.name).write_bytes(wheel.read_bytes())
        print(f"Qualified {wheel.name}")


if __name__ == "__main__":
    main()
