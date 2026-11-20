# Operations and errors

A catalog can contain several named databases. The file-backed provider manages
the journals and working files below that catalog's native database directory.
Open and close it through `Catalog` so the provider can apply its admission,
locking and recovery rules.

## Create, open and close

Copy this block, then the read-only, commit outcome and diagnostics blocks in
order into `operations.py`. Run `python operations.py` in a fresh directory
on a filesystem that supports durable creation. On Windows, use a local NTFS
directory.

```python
from gyldan_shared import Catalog

catalog = Catalog("./data")
with catalog.create("library") as database:
    identity = database.database_id()

with catalog.open(database_id=identity) as database:
    root = database.get_handle("main")
    print("Opened", database.database_id())
```

The script prints the UUID of the database it just created.
You can select an existing database by name, database UUID or root-journal
filename. `Catalog.databases()` lists catalog entries and their reported
problems. A session context manager closes its resources at exit. Use a fresh
session and fresh handles for subsequent work.

## Filesystem creation support

Fresh creation requires supported directory persistence operations. Current
native creation supports local Windows NTFS and the qualified Linux and macOS
routes. To try the best-effort option on Windows ReFS, save the example below as
`refs.py` and run `python refs.py` from a fresh directory on a local ReFS
volume.

```python
from gyldan_shared import Catalog

refs_catalog = Catalog("./refs-data")
with refs_catalog.create(
    "library", directory_durability="allow_best_effort",
) as database:
    for warning in database.creation_warnings:
        print(warning.message)
```

On that route, directory persistence remains unconfirmed and a crash can make
the database unreachable. The Python example prints the creation warning.
To try the same option from PowerShell, run this command on the ReFS volume.
The CLI writes its creation warning to standard error.

```powershell
gyldan-shared --catalog ./refs-cli-data create library --allow-best-effort-directory-creation
```

The default requires the durable creation route.

A creation error carrying `published_database_id` means publication happened
before the final directory flush failed. Inspect the catalog for that identity
before retrying creation.

## Read-only opens and durability

```python
with catalog.open(name="library", read_only=True) as database:
    root = database.get_handle("main")
    print(database.is_read_only())  # True
```

A read-only open can serve the last published working state while durable
journal commits still need writable recovery. A read-only reopen therefore has
limited use for deciding the outcome of an uncertain commit. Use transaction
identity and `transaction_outcome` when resolving that decision.

## Commit outcomes

`CommitOutcomeUnknown` supplies the handle and transaction UUIDs. Capture them
when handling the failure, then check from a fresh writable session. This
example also captures those UUIDs during a normal transaction so you can try
the lookup when the commit succeeds.

```python
from gyldan_core import CommitOutcomeUnknown, TransactionStatus

try:
    with catalog.open(name="library") as database:
        root = database.get_handle("main")
        with root.transaction():
            root.define_concept("Book", {"title": "string"})
        with root.transaction():
            book_id = root.create_record("Book", {"title": "Dune"})
            handle_uuid = root.get_id()
            transaction_uuid = root.reading(book_id, "title").view.transaction_uuid
except CommitOutcomeUnknown as error:
    handle_uuid = error.handle_uuid
    transaction_uuid = error.transaction_uuid

with catalog.open(name="library") as database:
    outcome = database.transaction_outcome(handle_uuid, transaction_uuid)
    if outcome.status is TransactionStatus.COMMITTED:
        print("committed", outcome.change_number)
    elif outcome.status is TransactionStatus.NOT_COMMITTED:
        print("not committed")
    else:
        print("outcome remains unknown")
```

On a normal run, the example prints `committed` followed by the change number.
An `unknown` result leaves the outcome unresolved. Automatic retries need an
application strategy for recognizing whether the requested effect already
happened.

## Error categories

| Exception | Meaning |
| --- | --- |
| `NotThere` | An instance, value or selected historical position is absent |
| `NotAcceptable` | An input or proposed schema/value is invalid |
| `NotAllowed` | The operation is invalid in the handle or session state |
| `WriterBusy` | Another transaction owns the selected handle's writer |
| `DatabaseRefused` | Storage cannot be opened or admitted as requested |
| `StagingIOError` | Record staging failed with a proven noncommit |
| `CommitOutcomeUnknown` | The commit outcome needs checking |
| `OSError` | An I/O operation failed |

The model exceptions expose a `reason` string. A proven staging failure rolls
back the failed transaction's live view and permits a later transaction after
the provider's internal recovery. A commit I/O failure can make the session
stale. Existing handles retain admitted readings; new handles, fixed views and
writes are refused with `stale_after_io_failure`. Open a fresh session to
continue.

## Diagnostics

```python
with catalog.open(name="library", log_level="debug") as database:
    root = database.get_handle("main")
```

Logging levels are `trace`, `debug`, `info`, `warning`, `error` and `critical`.
`log_level="off"` suppresses automatic logging. Set the `GYLDAN_ENABLE_LOGS`
environment variable to `debug` to enable logging without passing `log_level`.
This example writes to `data/.gyldan/logs/library.jrnl.log`.

The session owns the logger lifecycle. Closing it drains and joins its logging
worker. Diagnostic logs serve inspection and troubleshooting; the native
journal drives replay and transaction outcome.
