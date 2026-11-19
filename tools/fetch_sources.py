"""Fetch exactly the component commits recorded for this release."""

import argparse
import json
import os
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def load_pins():
    data = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    owner, pins = data["owner"], data["repositories"]
    if not re.fullmatch(r"[a-zA-Z0-9-]+", owner) or not pins:
        raise ValueError("Invalid source owner or empty source lock")
    for name, commit in pins.items():
        if not re.fullmatch(r"gyldan-[a-z0-9-]+", name):
            raise ValueError(f"Invalid source repository name {name!r}")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError(f"Expected a full Git commit for {name}")
    return owner, pins


def fetch_component(owner, name, commit, key, source_root):
    destination = source_root / name
    destination.mkdir()
    with TemporaryDirectory(prefix="gyldan-source-key-") as directory:
        temp = Path(directory)
        identity = temp / "key"
        identity.write_text(key, encoding="ascii", newline="\n")
        identity.chmod(0o600)
        config = temp / "ssh_config"
        config.touch()
        command = shlex.join(
            [
                "ssh",
                "-F",
                config.as_posix(),
                "-i",
                identity.as_posix(),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=30",
                "-o",
                "UserKnownHostsFile=" + (ROOT / "tools/github-known-hosts").as_posix(),
            ]
        )
        env = dict(os.environ, GIT_SSH_COMMAND=command, GIT_TERMINAL_PROMPT="0")
        commands = (
            ["git", "init", "--quiet"],
            [
                "git",
                "fetch",
                "--quiet",
                "--depth=1",
                f"git@github.com:{owner}/{name}.git",
                commit,
            ],
            ["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"],
        )
        for args in commands:
            result = subprocess.run(
                args, cwd=destination, env=env, capture_output=True, check=False
            )
            if result.returncode:
                raise RuntimeError(f"{name}: git {args[1]} failed")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=destination, text=True
    )
    if actual.strip() != commit:
        raise RuntimeError(f"{name}: fetched revision does not match the release lock")
    print(f"Fetched {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    owner, pins = load_pins()
    raw_keys = os.environ.pop("GYLDAN_SOURCE_KEYS", "")
    keys = json.loads(raw_keys) if raw_keys else {}
    if set(keys) != set(pins):
        raise SystemExit(
            "GYLDAN_SOURCE_KEYS must contain one deploy key per pinned repository"
        )
    args.destination.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [
            pool.submit(
                fetch_component, owner, name, commit, keys[name], args.destination
            )
            for name, commit in pins.items()
        ]:
            future.result()


if __name__ == "__main__":
    main()
