# Transactions and history

Each handle has its own transaction and committed change sequence. A writable
transaction captures its starting view, collects edits and commits them together.

Copy the Python blocks from [your first database](getting-started.md) into a
file named `history.py`, then append the blocks on this page in order. Run
`python history.py` in a fresh working directory. Each example opens its own
session and uses the tutorial's `catalog` and `book_id`.

## Edit atomically

```python
from gyldan import ObjectHandle

with catalog.open(name="library") as database:
    objects = ObjectHandle(database.get_handle("main"))
    book = objects.get(book_id)
    with objects.transaction() as transaction:
        book.title = "Dune Messiah"
        book.pages = 256
    print(transaction.change_number)

    try:
        with objects.transaction():
            book.title = "Temporary title"
            raise ValueError("cancel this edit")
    except ValueError:
        pass
    print(book.title)  # Dune Messiah
```

A normal exit commits. An exception escaping the transaction body rolls back
its edits and propagates to the caller. Catch an expected body error outside the
context so it triggers rollback. The example prints the acknowledged change
number and then the title that remained after rollback.

Writes need an active transaction. A second active transaction on the same
handle is refused. Another session holding that handle's writer can cause a
`WriterBusy` refusal. A transaction with no final changes keeps the current
committed change number.

## Capture a version

```python
with catalog.open(name="library") as database:
    objects = ObjectHandle(database.get_handle("main"))
    book = objects.get(book_id)
    before = objects.get_version()
    with objects.transaction():
        book.pages = 600

    old_objects = objects.at(before)
    print(old_objects.get(book_id).pages)  # 256
    print(book.pages)                     # 600
```

A version contains the selected handle's change number and its captured
ancestry coordinates. Change numbers belong to individual handles. Use the
complete version when you need to retain a layered view.

Historical handles are read-only. Selecting a version leaves the live handle
at its current state. The same instance UUID can be looked up in an earlier view
if the instance existed there.

## Use the Core handle when you need commit outcomes

The native session exposes Core handles as well as the object facade.

```python
from gyldan_core import CommitOutcomeUnknown

try:
    with catalog.open(name="library") as database:
        core_handle = database.get_handle("main")
        with core_handle.transaction():
            core_handle.set(book_id, "pages", 601)
        print(core_handle.record(book_id)["properties"]["pages"])  # 601
except CommitOutcomeUnknown as error:
    print(error.handle_uuid, error.transaction_uuid)
```

An uncertain outcome needs the transaction's identity to check what committed.
Keep that identity with the application's operation information. Open a fresh
session and call its `transaction_outcome(handle_uuid, transaction_uuid)` method.
The [commit outcomes example](operations.md#commit-outcomes) shows this lookup.

Commit I/O failures can retire a session's writing capability. Existing handles
retain their admitted readings, and new views or writes can be refused with
`stale_after_io_failure`. [Operations and errors](operations.md) explains how to
handle this state and the difference between staging and commit failures.
