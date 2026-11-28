# Install Gyldan

The `gyldan` package includes the Python object API, the native file-backed
provider, Core Python interfaces and validator support. Pip installs its runtime
dependencies.

## Create a virtual environment

Use a standard CPython installation matching one of the available wheels. Run
the commands for your shell from the directory where you want to work.

=== "Windows PowerShell"

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

=== "macOS or Linux (Bash or Zsh)"

    ```sh
    python3 -m venv .venv
    source .venv/bin/activate
    ```

Install `0.0.0a6` and check both entry points.

```sh
python -m pip install --upgrade pip
python -m pip install "gyldan==0.0.0a6"
python -m pip check
gyldan-shared --help
python -m gyldan_shared --help
```

To upgrade to the latest published prerelease, use
`python -m pip install --upgrade --pre gyldan`.
The available versions and files are listed on the [Gyldan PyPI page](https://pypi.org/project/gyldan/).

## Wheel platforms

Gyldan `0.0.0a6` has wheels for CPython 3.12, 3.13, 3.14 and 3.15 on these
platforms.

| Platform | Wheel requirement |
| --- | --- |
| Windows | 64-bit AMD64 CPython |
| macOS | macOS 26 or newer, Apple Silicon or Intel |
| Linux | AMD64 or ARM64, glibc 2.34 or newer |
| Raspberry Pi | 64-bit ARM Linux with glibc 2.34 or newer |

Select a wheel matching the interpreter and operating system. For example,
32-bit Raspberry Pi OS needs a different build from the ARM64 wheels. A
manylinux wheel's compatibility baseline describes the Linux runtime it needs.
The ARM release build is tested on GitHub's ARM Linux runner.

If pip reports that it cannot find a matching distribution, check
`python --version`, interpreter architecture and the files listed for that
release. The package includes native code, so those details determine which
wheel pip can install.

## Check your installation

```sh
python -c "from importlib.metadata import version; print(version('gyldan'))"
python -c "from gyldan import ObjectHandle; from gyldan_shared import Catalog; print('Gyldan imports successfully')"
```

If you installed `0.0.0a6`, you should see the following output.

```text
0.0.0a6
Gyldan imports successfully
```

Continue with [your first database](getting-started.md).
