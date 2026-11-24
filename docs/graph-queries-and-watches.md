# Graph queries and change notifications

A graph selection describes which records a caller needs from a Core handle.
Named rules can start from record IDs or a concept scan, follow references, and
combine or filter the resulting sets. Each rule requests full fields, a
caller-defined summary, or a reference. If several rules reach a record,
the result includes its highest requested detail and the names of all the
rules that reached it. An application can use a selection to represent a
saved lens for a role or task.

On Native Shared, Gyldan evaluates the selection in C++. A query watch
tracks a selection and reevaluates affected work after the handle's committed
view advances.

!!! note "Development build"
    This API requires a current alpha build that provides
    `gyldan_core.graph` and `Catalog.open_changes()`. The published
    `0.0.0a2` wheel predates these APIs.

## Build and watch a selection

Run [Concepts and objects](concepts-and-objects.md) to create
`./concepts-data`. The example watches books and their authors on the live
`main` handle. It uses separate read and write sessions so the watcher can
advance after a commit.

```python
import asyncio
from contextlib import aclosing

from gyldan import ObjectHandle, instance_id
from gyldan_core.graph import Detail, Follow, Rule, Scan, Selection, Step, watch_selection
from gyldan_shared import Catalog


async def main():
    catalog = Catalog("./concepts-data")
    books = Scan("Book")
    selection = Selection(
        (
            Rule("books", books, Detail.SUMMARY),
            Rule("authors", Follow(books, (Step("author"),)), Detail.REF),
        ),
        summaries={"Book": ("title", "pages")},
    )

    with catalog.open(name="library") as writer:
        database_id = writer.database_id()
        objects = ObjectHandle(writer.get_handle("main"))

        async with catalog.open_changes(database_id, handle="main") as changes:
            with catalog.open(database_id=database_id, read_only=True) as reader:
                handle = reader.get_handle("main")
                async with aclosing(watch_selection(changes, handle, selection)) as deltas:
                    initial = await anext(deltas)
                    print(f"Initial selection contains {len(initial.added)} records")

                    with objects.transaction():
                        book = objects.create("Book", title="Emma", pages=474)
                        book_id = instance_id(book)

                    delta = await asyncio.wait_for(anext(deltas), timeout=10)
                    print(delta.added[book_id].values["title"].value)  # Emma


asyncio.run(main())
```

Without a baseline, the first item contains the current selection in
`added`, with `from_version=None`. Later items report newly selected records
in `added`, UUIDs that left the selection in `removed`, and selected records
whose delivered data or metadata changed in `updated`. The versions identify
the complete handle views on either side of each delta. A record leaving the
selection can still exist in the database.

## Resume after a restart

After applying a delta, persist its `to_version` when you acknowledge that
delivery. When restarting the same watch, reopen the change handle and live
Core reader, then pass the acknowledged `Version` to
`watch_selection(changes, handle, selection, params, since=version)`. Retain
all of the version's layer UUID and change-number pairs in order so you can
reconstruct it. Use the same database, handle, selection and parameters. If
those change, start with a fresh selection.

A resumed watch compares the acknowledged state with the current state and
yields a catch-up delta if the result differs. Multiple commits can be
coalesced into a single delta. A commit that leaves the delivered result
unchanged produces no query delta.

## Watch commits directly

`Catalog.open_changes()` reports changes to the handle's committed view.
Filesystem activity prompts an early check, and a periodic check remains active.
Set `notify=False` to use periodic checking alone. A direct change handle
supports synchronous and asynchronous reads and can include the initial version.
See the [Python reference](python-reference.md#graph-selections-and-change-notifications)
for the signatures and lifecycle.
