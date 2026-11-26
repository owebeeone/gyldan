# Schema migrations

A schema migration changes the fields or validators of an existing concept.
Record IDs, concept identity and committed history are preserved. The database
stores the converter's Python source and class name in a Migration record
linked to the exact old and new definitions.

The examples run in order against a fresh native database, using
`gyldan.ObjectHandle` and `gyldan.migrations`. The
[runnable version](examples/schema_migrations.py) contains the complete flow
with its checks:

```sh
python schema_migrations.py /path/to/fresh-catalog
```

If your conversion depends on other records or handles, start with
[what to avoid](#what-to-avoid).

## Split one field into two

Set up a fresh database, install migration support and keep a fixed view of the
original record. Configure the runner on the idle handle. It will execute
trusted stored Python.

```python
from gyldan import ObjectHandle, concept, concept_property, instance_id
from gyldan.migrations import (
    check_migrations,
    configure_runner,
    install,
    prepare_schema_change,
    run_migrations,
    stage_schema_change,
)
from gyldan_shared import Catalog

database = Catalog("./migration-data").create("runs")
root = database.get_handle("main")
handle = ObjectHandle(root)
configure_runner(handle)

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
```

Declare the target definition under the existing concept name. The converter
reads the immutable old record and assigns the two required fields on the new
record. Gyldan carries compatible values such as `title`. A negative or missing
duration fails preflight because this converter cannot produce a valid target.

```python
@concept(name="Run")
class SplitRun:
    title: str
    whole_minutes: int = concept_property(required=True)
    remaining_seconds: int = concept_property(required=True)

source = """\
class SplitDuration:
    def migrator(self, old, new):
        seconds = old.duration_seconds
        if seconds is None or seconds < 0:
            raise ValueError("Expected a nonnegative duration")
        new.whole_minutes, new.remaining_seconds = divmod(seconds, 60)
"""

proposal = {
    "name": "split_duration",
    "definition": SplitRun,
    "migrator": {"source": source, "class_name": "SplitDuration"},
}
prepared = prepare_schema_change(handle, proposal)
report = check_migrations(prepared)
assert report.complete and report.eligible and report.token is not None

with handle.transaction() as transaction:
    stage_schema_change(transaction, prepared, report.token)
```

Preflight runs before the write transaction. Its eligible token authorizes
staging. Successful exit from the transaction publishes the schema and Migration
record together. The existing live reference `run` follows the new definition
when it is read. A read-triggered conversion is pending work in its transaction.

```python
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
```

The first rollback discards the record conversion. The already committed schema
remains published. The bulk call then converts the record in the next
transaction. Its second call returns zero because the record is already staged.
Rollback of the original **publication** transaction would have discarded the
schema and Migration record together.

## Add a field with a default

Continue from the split example. A compatible optional addition can use an
ordinary schema edit. With no stored assignment, a read uses the declared
default and leaves the record's change number alone.

```python
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
```

## Preview a validator before publishing

This example adds a nonnegative rule for `Task.estimate_hours`. An overlay
already has an invalid estimate. Both views contain the **same record ID**
with their own effective values. Preflight assesses each view separately.

```python
from gyldan_core import HandleEnum, NotAcceptable
from gyldan_core.migrations import MigrationOutcome
from gyldan_core.validation import value

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
```

Close the session when the work is done.

```python
database.close()
```

The default `retain_existing` policy can preserve a previously stored invalid
value. An explicit assignment still has to pass the new validator. Use
`require_repair` when every affected record must pass before publication.

## What to avoid

**Keep every converter's data inputs on the record being migrated.** This is
the supported alpha scope, including when two records are visible from the
same handle. A lookup through a reference, a query for a second record, or
opening another handle to retrieve a value takes the conversion outside that
scope. Some such reads are possible through Python. Their results have no
correctness guarantee. For example, a live overlay and its parent can see
different settings, and a COW child keeps its birth view of the parent.
Preflight eligibility provides no guarantee for a converter that joins those
views or reads other records.

If a Run's conversion depends on a setting in another handle, resolve it in
ordinary application code before preflight:

1. Choose the source handles and committed versions. Read the settings and
   resolve differences explicitly.
2. In an ordinary transaction on the handle whose data you will migrate, write
   the chosen input onto each affected Run, for example
   `offset_seconds_at_cutover`. Account for any views with local overrides.
   Commit the inputs before preparing the proposal.
3. Have the converter read `old.duration_seconds` and
   `old.offset_seconds_at_cutover` from the same Run. If the chosen settings
   change before publication, update those inputs and assess again.

Application code owns the ordering and reconciliation of those separate handle
transactions. For workflows that join, split or update multiple records, use
ordinary application transactions. Passing a concept to `run_migrations` runs
a record-local converter for each selected record and still follows this rule.

Also avoid these mistakes:

- Opening a transaction, writing to the database, or performing external side
  effects inside `migrator`. Preflight can invoke it as a trial, and rollback
  cannot undo external actions. Read `old` and stage output through `new`.
- Preparing or checking inside the staging transaction, or trying to reuse a
  stale token. End the failed attempt, prepare again and check the fresh view
  before opening another write transaction.
- Enabling a runner for untrusted stored code, or relying on live reads to
  commit conversions. Use an explicit transaction or finish the transaction
  opened by the read.

## Reference

`gyldan.migrations` is the application API. Use a writable
`gyldan.ObjectHandle` when publishing or materializing conversions. Prepare
and assess on an idle handle before opening the publication transaction.

### Entry points

| Call | Input and effect |
| --- | --- |
| `install(handle)` | Install the migration vocabulary in the active writable transaction. Commit that transaction before preparing a proposal. Returns `None`. |
| `configure_runner(handle)` | Set the built-in `PythonMigrationRunner` on the idle endpoint. Returns `None`. |
| `configure_runner(handle, runner)` | Use the supplied runner on the idle endpoint. Pass `None` to clear it. A reopened endpoint that needs to execute stored Python must have a suitable runner configured. |
| `prepare_schema_change(handle, proposal)` | Normalize the proposal and capture the committed publishing view. Returns `PreparedMigration`. A transaction already open on that handle is refused. |
| `check_migrations(prepared, *, report=None)` | Assess the prepared change against the committed views. Returns `MigrationReport`. An optional callback consumes each `MigrationReportRow`. This operation opens no writer and stores no conversions. |
| `stage_schema_change(transaction, prepared, token)` | Stage the schema and Migration record together in the supplied active transaction. Returns `None`. The caller commits or rolls back. The transaction must belong to the same endpoint at the assessed base and the token must come from that exact prepared object. |
| `run_migrations(handle, concept)` | Stage pending conversions for visible records of the concept and its derived concepts. Pass a concept name or an object for the concept from the same handle. Requires an active writable transaction. Returns the count newly converted by this call. Already staged or applied records are excluded. |
| `migration_view(record)` | Inside a callback, expose the tagged-value view of the generated `old` or `new` record for typed keys and explicit slot operations. |

The `install`, `stage_schema_change` and `run_migrations` functions borrow the
caller's transaction. A failed conversion or validation in a bulk run
discards that run's batch and preserves earlier pending work in the attempt.
If the exception leaves a transaction context, the context rolls back that
transaction. See [transactions and visibility](transactions-and-history.md).

### Proposals

Pass a mapping with the fields below. The `definition` names an existing
concept and supplies its target declared fields. A field in that concept's
own definition that is omitted from the target is removed. Inherited fields
are carried separately. Advanced callers can pass a typed
`gyldan_core.migrations.MigrationProposal` with an explicit target graph.

| Key | Meaning | Default |
| --- | --- | --- |
| `definition` | A `@concept` declaration for the target definition of the existing concept. Use `@concept(name="ExistingName")` if the Python class has a different name. | Required |
| `name` | Identifier stored with the migration. | `"migration"` |
| `migrator` | A mapping with exactly `source` and `class_name`. Supply Python source text and the converter class it defines. Preparing this mapping requires a configured runner to capture the runtime manifest. | `None` |
| `validator_policy` | Use `"retain_existing"` to permit an existing invalid value to remain under the retention rules, or `"require_repair"` to block publication until affected values pass. New assignments must satisfy the validator under either policy. | `"retain_existing"` |
| `depends_on` | UUIDs of committed Migration records required by this proposal. | Empty |
| `input_definitions` | UUIDs of the source field definitions used by the converter. | Empty |
| `output_definitions` | UUIDs of the target field definitions the converter is authorized to write. | Empty |

For a scripted merge that maps selected fields across a transition, declare the
exact input and output definition UUIDs. Use the committed schema descriptors for
inputs and `prepared.proposal.target_graph` for normalized target descriptors.
If target UUIDs were assigned during preparation, you can use
`dataclasses.replace` on `prepared.proposal` to add the declarations, then
prepare and assess that typed proposal again. Use the resulting prepared object
and its token when staging.

### Reports and retries

| Field on `MigrationReport` | Meaning |
| --- | --- |
| `complete` | The requested assessment completed. |
| `eligible` | The report can authorize staging. |
| `blocking_count` | Number of blocking findings. |
| `counts` | Pairs of `MigrationOutcome` and count. |
| `token` | The assessment token for this eligible report, or `None`. |

The optional `report(row)` callback returns `True` to continue or `False` to
stop. A stopped scan is incomplete and supplies no staging token. Use the
callback to collect or display rows. Keep model writes and transaction
operations outside the callback.

Each row identifies its database, handle UUID and label, committed version,
record and actual concept, and the relevant definition, property, key,
migration and step when available. `outcome` is one of
`passes_unchanged`, `passes_after_conversion`, `repair_required`,
`conversion_failed` or `unreadable`. Check `reason` and
`blocks_publication` alongside the outcome. For example, a retained invalid
value can require repair without blocking publication.

An intervening write or topology change can invalidate the assessment. If
staging or commit refuses a stale token, end the failed attempt if still
active, then prepare and check again before opening another write
transaction. Treat uncertain I/O outcomes according to the provider's
[recovery rules](storage-and-recovery.md).

| Error or reason | What to check |
| --- | --- |
| `transaction_open` or `no_transaction` | Prepare and check on an idle handle. Stage in the supplied active attempt and bulk-convert in an active writable attempt. |
| `migration_token_stale` or `migration_capture_changed` | Check endpoint, transaction base and token ownership, then reassess if the capture changed. |
| `migration_runner_unavailable`, `migration_runtime_mismatch` or `migration_dependency_changed` | Check runner configuration and the expected runtime and module manifest. |
| `migration_requires_write` | A live read needs conversion on a read-only endpoint. Use a writable endpoint for the conversion. |
| `MigrationFailed` | Inspect the migration, handle and record UUIDs, phase, property or key where applicable, and the original Python cause when available. |
| `SchemaChanged` | Refresh the affected schema view and assess the proposed change against the current definitions. |
| `migration_dependency_missing` or `migration_conflict` | A merge lacks a compatible approved path or complete selection, or encounters incompatible interpretations. A refused hop leaves the parent unchanged. |

### Converter and runner

Define `migrator(old, new)` on the named class. The runner supplies generated
objects for the exact source and target definitions. Read the immutable
`old` object and assign to `new`. Compatible fields may already be carried
into `new`. Treat both objects as callback-scoped. For explicitly tagged
reads and writes, use `migration_view(old)` or `migration_view(new)`.
The old view offers `get` and `keys`, and the new view also offers `set`
and `remove`.

Enable execution only for stored Python you trust. The built-in runner can
be constructed as `PythonMigrationRunner(*, modules=(), resolver=None)`.
Pass declared module names in `modules`. The optional `RuntimeResolver`
supplies `environment_digest()` and `module_digest(name)` for host
attestation. Omission uses the built-in local resolver. Preflight can run
the converter to validate a detached candidate. Keep it free of database
mutations, transaction lifecycle calls and external side effects.

!!! warning "Alpha converters are record-local"
    All record data used by a converter must come from the record being
    migrated. This applies to another record on the same handle, a reference
    followed to a different record, and records visible only on a parent,
    child, overlay or COW handle. The callback surface can permit cross-record
    reads. Their correctness is unsupported even if preflight succeeds.
    Resolve multi-record inputs in application code and commit the chosen
    values onto the records before assessment.

### Live reads, history and direct-parent merge

- A live read of an old record can stage its conversion in the active
  transaction or start a migration transaction on a writable idle handle.
  It does not commit. Finish the attempt with commit or rollback, or adopt
  a read-started attempt with a normal transaction context. An existing live
  reference follows the converted values. A fixed historical view keeps its
  captured definition and data.
- Committing records the converted values and their receipts. Reopen and
  journal replay restore committed results without executing the converter
  again. Rollback discards pending conversions. Publish each schema transition
  separately. A lazy record can then traverse the approved ordered chain in
  one conversion transaction.
- An overlay uses its effective source values, including local overrides. A
  conversion it commits writes its output locally. Those output fields
  shadow later parent writes, while untouched fields retain normal inheritance.
  A COW child keeps its captured birth ancestry and publishes its own local
  changes. A later parent migration does not become authority for that child.
- Merge is evaluated one direct parent at a time against its prospective
  schema, including eligible definitions staged by that hop. Where conversion
  is required, the receiver needs its own approved exact path and sufficient
  selection. Include the full declared inputs for mapped fields, including
  applicable keyed and scalar slots. A successful hop writes only the parent.
  The child's local state stays unchanged and its effective view follows
  ordinary handle semantics. See [handles and layers](handles-and-overlays.md).
