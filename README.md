# Gyldan

The public release repository for GyldanDB.

Each release will build and test pinned revisions of the component repositories
to produce the C++ SDK, the `gyldan` Python wheels, and matching product
documentation.

This repository is the home for release inputs, packaging code, and the
documentation publishing workflow. The component repositories own the
implementation that goes into each release.

## User documentation

The [Gyldan documentation site](https://owebeeone.github.io/gyldan/) covers
installation, concepts, objects, transactions and history. It includes a runnable
example and command-line workflows. You can also read the
[user guide in this repository](https://github.com/owebeeone/gyldan/blob/main/docs/index.md).

To build the documentation locally, run these commands from the release
repository root with a Python virtual environment active.

```sh
python -m pip install -r requirements-docs.txt
python -m mkdocs build --strict
```

To preview the site, run the following command and open the local address it
prints. Press Ctrl+C to stop the server.

```sh
python -m mkdocs serve
```

## Python release builds

Run **Build and publish Gyldan** from GitHub Actions to build and verify wheels
for a version. The workflow uses the commits recorded in `sources.lock.json`
and produces one `gyldan` wheel per platform and CPython version.

The matrix covers CPython 3.12 through 3.15 on Windows AMD64, macOS 26 Intel
and Apple Silicon, Linux AMD64, and Linux ARM64 for 64-bit Raspberry Pi OS.
The Linux wheels target the manylinux 2.34 baseline. GitHub's ARM Linux runner
builds and tests the ARM wheel in that build environment.

A tag such as `v0.0.0a5` runs the same checks, publishes the complete wheel
set to PyPI through Trusted Publishing, and creates a GitHub prerelease with
the wheels and checksums. A manual workflow run produces build artifacts.

The workflow reads the private components using the `GYLDAN_SOURCE_KEYS`
Actions secret. Each key is a read-only GitHub deploy key for one pinned repo.
PyPI publishing uses the `publish.yml` Trusted Publisher and the `pypi` Actions
environment.
