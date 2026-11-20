"""Exercise the single installed distribution through its native provider."""

import subprocess
import sys
import tempfile
from importlib.metadata import distributions, metadata, version
from pathlib import Path

from gyldan_core.validation import value
from gyldan_shared import Catalog

from gyldan import ObjectHandle, concept, concept_property


@concept
class Task:
    rank: int = concept_property(validator=value >= 0)


def main(expected_version):
    installed = {
        item.metadata["Name"]
        for item in distributions()
        if item.metadata["Name"].startswith("gyldan")
    }
    assert installed == {"gyldan"}
    assert version("gyldan") == expected_version
    package_metadata = metadata("gyldan")
    readme = Path(__file__).resolve().parents[1] / "README.md"
    assert package_metadata["Description"] == readme.read_text(encoding="utf-8")
    assert package_metadata["Description-Content-Type"] == "text/markdown"
    assert (
        "Documentation, https://owebeeone.github.io/gyldan/"
        in package_metadata.get_all("Project-URL")
    )
    launcher = Path(sys.executable).with_name(
        "gyldan-shared.exe" if sys.platform == "win32" else "gyldan-shared"
    )
    subprocess.run([str(launcher), "--help"], check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix="gyldan-smoke-") as temporary:
        catalog = Catalog(Path(temporary) / "catalog")
        with catalog.create("wheelcheck") as database:
            handle = ObjectHandle(database.get_handle("main"))
            with handle.transaction():
                handle.define(Task)
            before = handle.get_version()
            with handle.transaction():
                handle.define(Task)
            assert handle.get_version() == before
            with handle.transaction():
                task = handle.create("Task", rank=1)
            assert task.rank == 1


if __name__ == "__main__":
    main(sys.argv[1])
