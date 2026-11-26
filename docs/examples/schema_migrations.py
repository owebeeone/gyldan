"""Evolve a concept with schema migrations in a fresh native catalog.

Usage: python schema_migrations.py /path/to/fresh-catalog
Requires an installed gyldan wheel and supported native creation. The database
is retained after the example; rerunning the same name refuses it.
"""
import argparse
from pathlib import Path

from gyldan import ObjectHandle, concept, concept_property, instance_id
from gyldan.migrations import (
    check_migrations,
    configure_runner,
    install,
    prepare_schema_change,
    run_migrations,
    stage_schema_change,
)
from gyldan_core import HandleEnum, NotAcceptable
from gyldan_core.migrations import MigrationOutcome
from gyldan_core.validation import value


# The converter is stored in the database as Python source, so it is written
# at module level, with no indentation of its own.
SPLIT_DURATION_SOURCE = """\
class SplitDuration:
    def migrator(self, old, new):
        seconds = old.duration_seconds
        if seconds is None or seconds < 0:
            raise ValueError("Expected a nonnegative duration")
        new.whole_minutes, new.remaining_seconds = divmod(seconds, 60)
"""


def run(root):
    """The tutorial's three examples, on the supplied root provider handle."""
    handle = ObjectHandle(root)
    configure_runner(handle)

    # Split one field into two: set up.
    @concept(name="Run")
    class OriginalRun:
        title: str
        duration_seconds: int

    with handle.transaction():
        install(handle)
        handle.define(OriginalRun)

    with handle.transaction():
        run = handle.create("Run", title="Nightly run", duration_seconds=125)

    run_id = instance_id(run)
    old_run = handle.at(handle.get_version()).get(run_id)

    # Declare the target and publish it.
    @concept(name="Run")
    class SplitRun:
        title: str
        whole_minutes: int = concept_property(required=True)
        remaining_seconds: int = concept_property(required=True)

    proposal = {
        "name": "split_duration",
        "definition": SplitRun,
        "migrator": {"source": SPLIT_DURATION_SOURCE, "class_name": "SplitDuration"},
    }
    prepared = prepare_schema_change(handle, proposal)
    report = check_migrations(prepared)
    assert report.complete and report.eligible and report.token is not None

    with handle.transaction() as transaction:
        stage_schema_change(transaction, prepared, report.token)

    # Convert on read, roll back, then convert in bulk.
    published = handle.get_version()
    with handle.transaction():
        assert (run.whole_minutes, run.remaining_seconds) == (2, 5)
        handle.rollback()

    assert handle.get_version() == published
    assert old_run.duration_seconds == 125

    with handle.transaction():
        assert run_migrations(handle, "Run") == 1
        assert run_migrations(handle, "Run") == 0

    assert instance_id(run) == run_id
    assert (run.whole_minutes, run.remaining_seconds) == (2, 5)
    assert old_run.duration_seconds == 125

    # Add a field with a default.
    @concept(name="Run")
    class RunWithMode:
        title: str
        whole_minutes: int = concept_property(required=True)
        remaining_seconds: int = concept_property(required=True)
        execution_mode: str

    fixed_run = handle.at(handle.get_version()).get(run_id)
    last_record_change = root.last_change_number(run_id)

    with handle.transaction():
        definition = handle.define(RunWithMode)
        definition.properties["execution_mode"].default = "batch"

    before_read = handle.get_version()
    assert run.execution_mode == "batch"
    assert root.last_change_number(run_id) == last_record_change
    assert handle.get_version() == before_read
    assert not hasattr(fixed_run, "execution_mode")

    # Preview a validator before publishing.
    @concept(name="Task")
    class OriginalTask:
        estimate_hours: int

    @concept(name="Task")
    class CheckedTask:
        estimate_hours: int = concept_property(validator=value >= 0)

    with handle.transaction():
        handle.define(OriginalTask)
    with handle.transaction():
        task = handle.create("Task", estimate_hours=4)

    task_id = instance_id(task)
    overlay = ObjectHandle(root.create_handle(HandleEnum.OVERLAY))
    with overlay.transaction():
        overlay.get(task_id).estimate_hours = -2

    proposal = {"name": "nonnegative_estimate", "definition": CheckedTask}
    strict = prepare_schema_change(
        handle, {**proposal, "validator_policy": "require_repair"}
    )
    blocked = check_migrations(strict)
    assert blocked.complete and not blocked.eligible and blocked.token is None

    rows = []

    def collect(row):
        rows.append(row)
        return True

    retained = prepare_schema_change(handle, proposal)
    stopped = check_migrations(retained, report=lambda row: False)
    assert not stopped.complete and stopped.token is None

    report = check_migrations(retained, report=collect)
    assert report.complete and report.eligible and report.token is not None
    assert any(
        row.record == task_id
        and row.handle == overlay.get_version().layers[0].handle_uuid
        and row.outcome == MigrationOutcome.REPAIR_REQUIRED
        and row.reason == "validator_failed"
        and not row.blocks_publication
        for row in rows
    )

    with handle.transaction() as transaction:
        stage_schema_change(transaction, retained, report.token)

    with overlay.transaction():
        estimate = overlay.get(task_id)
        assert estimate.estimate_hours == -2
        try:
            estimate.estimate_hours = -2
        except NotAcceptable as error:
            assert error.reason == "validator_failed"
        else:
            raise AssertionError("Expected the explicit invalid assignment to fail")
        estimate.estimate_hours = 2

    with handle.transaction():
        assert task.estimate_hours == 4
    assert overlay.get(task_id).estimate_hours == 2
    return {"run": run_id, "task": task_id}


def main(path):
    from gyldan_shared import Catalog

    with Catalog(path).create("migrations") as database:
        print("Migrated:", run(database.get_handle("main")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="A fresh directory for the example catalog")
    main(parser.parse_args().path)
