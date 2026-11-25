# Graph queries and change notifications

A graph selection describes the records a caller needs from one Core handle.
Named rules can start from identities or a concept scan, follow references,
filter records, and combine sets. Each rule requests full fields, a summary,
or a reference. Gyldan combines results by record UUID, keeping the highest
requested detail and all the rule names that reached the record.

An application can compile a saved lens into a selection. The application owns
the lens definition, authorization, display order, and delivery protocol. On
Native Shared, Gyldan evaluates selections in C++. A query watch advances a
tracked selection as the handle's committed view changes.

!!! note "Development build"
    This API requires a current alpha build that provides
    `gyldan_core.graph` and `Catalog.open_changes()`. The published
    `0.0.0a2` wheel predates these APIs.

## Build and advance a parameterized lens

This example uses the in-memory Reference provider from `gyldan-test-py`.
Select one author and find books that point to that author. The inward step
names the concept on the referencing side, `Book`. Supply the selected author's
UUID as a parameter so the same selection can serve different authors.

```python
from gyldan import ObjectHandle, concept, instance_id
from gyldan_core import graph
from gyldan_testing import MemoryStorage


@concept
class Author:
    name: str


@concept
class Book:
    title: str
    pages: int
    author: Author | None


database = MemoryStorage()
handle = database.get_handle("root")
objects = ObjectHandle(handle)
with objects.transaction():
    objects.define(Author)
    objects.define(Book)
with objects.transaction():
    author = objects.create("Author", name="Jane Austen")
    other_author = objects.create("Author", name="Mary Shelley")
    book = objects.create("Book", title="Emma", pages=474, author=author)
    objects.create("Book", title="Unattributed notes", pages=6)

focus = graph.Param("author")
books = graph.Follow(focus, (graph.Step("author", graph.Direction.IN, "Book"),))
linked_books = graph.Where(graph.Scan("Book"), graph.Exists((graph.Step("author"),)))
selection = graph.Selection(
    (
        graph.Rule("focus", focus, graph.Detail.REF),
        graph.Rule("books", books, graph.Detail.SUMMARY),
    ),
    summaries={"Book": ("title",)},
)
params = {"author": instance_id(author)}
book_id = instance_id(book)
assert graph.evaluate_set(handle, linked_books) == {book_id}
first = graph.evaluate_tracked(handle, selection, params)
assert first.result.records[book_id].values["title"].value == "Emma"
assert not first.result.records[instance_id(author)].values

with objects.transaction():
    book.pages = 475
second = graph.advance(handle, first)
assert second.delta.updated[book_id].values == first.result.records[book_id].values
assert second.delta.updated[book_id].changes != first.result.records[book_id].changes

with objects.transaction():
    book.author = other_author
third = graph.advance(handle, second.tracked)
assert third.delta.removed == {book_id}
assert objects.get(book_id).title == "Emma"

full = graph.delta(handle, selection, first.result.version, third.delta.to_version, params)
assert full.removed == {book_id}
```

The separate `Where` query finds books with an author and skips unlinked books.
The page count is outside the summary. Editing it still updates the delivered
record because its edit-precondition metadata changed. Moving the book to a
different author removes it from this lens while leaving it in the database.
Keep `Advance.tracked` for the next advance, even when its delta is empty.
`graph.delta` independently evaluates both versions and is useful when you
have two versions and no tracked state. See the
[operator and result reference](python-reference.md#graph-selections-and-change-notifications).

## Watch, save a checkpoint, and resume

Run [Concepts and objects](concepts-and-objects.md) first to create the
`library` database under `./concepts-data`. This example uses a live Core
reader and a separate writer on the same handle. It watches book titles,
applies the first snapshot and a live update, then reconnects after a write
made while the watch is closed.

Save the three blocks below in order as `watch_books.py`. The checkpoint
contains both the applied rows and the complete ordered version. It lives
in a temporary directory for the demonstration. For recovery across process
restarts, use a persistent destination. In an application, store
both together under the database, handle, selection and parameter identity
before acknowledging the delivery.

```python
import asyncio
from contextlib import aclosing
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from gyldan import ObjectHandle, instance_id
from gyldan_core import LayerChange, Version, graph
from gyldan_shared import Catalog


def version_of(state):
    if state is None:
        return None
    return Version(tuple(LayerChange(*layer) for layer in state["layers"]))


def apply_and_save(path, state, delta):
    if delta.from_version is None:
        rows = {}
    elif delta.from_version == version_of(state):
        rows = dict(state["rows"])
    else:
        raise ValueError("Delta has the wrong base. Start from a fresh snapshot.")

    for identity in delta.removed:
        rows.pop(identity, None)
    for changes in (delta.added, delta.updated):
        for identity, record in changes.items():
            title = record.values.get("title")
            rows[identity] = title.value if title is not None else None

    state = {
        "layers": [
            [layer.handle_uuid, layer.change_number]
            for layer in delta.to_version.layers
        ],
        "rows": rows,
    }
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(state), encoding="utf-8")
    pending.replace(path)
    return state


async def apply_watch_delta(path, state, delta, reader, selection):
    base = version_of(state)
    if base is not None and delta.from_version not in (None, base):
        # The watch can advance over commits that changed no selected rows.
        delta = await asyncio.to_thread(
            graph.delta, reader, selection, base, delta.to_version
        )
    return apply_and_save(path, state, delta)


def write_book(catalog, database_id, handle_name, title, identity=None):
    with catalog.open(database_id=database_id) as writer:
        objects = ObjectHandle(writer.get_handle(handle_name))
        with objects.transaction():
            if identity is None:
                book = objects.create("Book", title=title)
            else:
                book = objects.get(identity)
                book.title = title
        return instance_id(book)
```

```python
async def watch_books(catalog, database_id, handle_name):
    selection = graph.Selection(
        (graph.Rule("books", graph.Scan("Book"), graph.Detail.SUMMARY),),
        summaries={"Book": ("title",), "IllustratedBook": ("title",)},
    )
    with TemporaryDirectory() as directory:
        checkpoint = Path(directory) / "books.json"
        async with catalog.open_changes(database_id, handle=handle_name) as changes:
            with catalog.open(database_id=database_id, read_only=True) as database:
                reader = database.get_handle(handle_name)
                async with aclosing(graph.watch_selection(changes, reader, selection)) as watch:
                    initial = await anext(watch)
                    state = apply_and_save(checkpoint, None, initial)
                    book_id = await asyncio.to_thread(
                        write_book, catalog, database_id, handle_name, "Emma"
                    )
                    added = await asyncio.wait_for(anext(watch), timeout=10)
                    state = await apply_watch_delta(checkpoint, state, added, reader, selection)
                    assert state["rows"][book_id] == "Emma"

        # The original stream is closed and both old handles are released.
        await asyncio.to_thread(
            write_book, catalog, database_id, handle_name, "Emma (revised)", book_id
        )
        restored = json.loads(checkpoint.read_text(encoding="utf-8"))
        async with catalog.open_changes(database_id, handle=handle_name) as changes:
            with catalog.open(database_id=database_id, read_only=True) as database:
                reader = database.get_handle(handle_name)
                async with aclosing(graph.watch_selection(
                    changes, reader, selection, since=version_of(restored),
                )) as watch:
                    caught_up = await asyncio.wait_for(anext(watch), timeout=10)
                    state = await apply_watch_delta(
                        checkpoint, restored, caught_up, reader, selection
                    )
                    assert state["rows"][book_id] == "Emma (revised)"
```

```python
if __name__ == "__main__":
    catalog = Catalog("./concepts-data")
    with catalog.open(name="library", read_only=True) as database:
        database_id = database.database_id()
    asyncio.run(watch_books(catalog, database_id, "main"))
```

A watch without `since` yields a full snapshot even if the selection is empty.
A resumed watch yields no immediate item if the result is unchanged. Multiple
commits can be coalesced, and an unrelated commit may yield no query delta.
The watch still advances internally, so the next nonempty delta can have a
`from_version` newer than the last delivered version. The example computes a
delta from its own checkpoint on such a gap. Only do this for the same
database, handle, selection and parameters when both versions are available.
If a saved version is unavailable, the scope changed, or the receiver lacks
the matching local rows, reopen without `since` and replace the view with a
fresh snapshot.

## Apply updates in an active UI

The Gyld Concepts view illustrates the boundary. Its server takes a committed
view of the authorized handle, projects schema records, and sends a snapshot
followed by versioned patches. It uses `ChangeHandle` and
`graph.changes_between` to update this custom projection. It rebuilds on an
ancestry mismatch or a migration head change. Its browser tracks the selected
scope and applied version independently. That snapshot, delta and provenance
protocol belongs to the application.

The Gyld saved-lens runner uses `graph.evaluate_tracked` and `graph.advance`
to refresh candidate records on the authorized handle. It keeps its own
display projection and rebuilds the tracked selection when the prior version
cannot advance to the target. This lets the app reuse Gyldan's query work
while controlling what rows and metadata it sends to the browser.

The same consumer rules apply to forwarded `SelectionDelta` values and custom
projections.

| Situation | Consumer behavior |
| --- | --- |
| A new watch or a change of handle, filters, or parameters | Cancel the old subscription and reject late frames for that scope. Replace all rows on the new snapshot, including an empty one. |
| One screen shows data from several handles | Keep a separate query and applied version for each handle. Combine the delivered rows in the application. |
| A patch arrives | Check its base against the last applied version. Remove departed UUIDs, upsert added and updated rows, and then re-sort for display. For a version gap, recompute from a valid checkpoint or request a fresh snapshot. An application that forwards deltas can do this on its server before sending a patch. |
| Provenance, permissions or edit metadata arrive separately | Apply them only to the matching scope and data version. Refresh edit tokens even when displayed fields are unchanged. |
| The stream disconnects | Reopen from the last checkpoint that was actually applied, or replace the cache with a new snapshot. Back off on transient failures. Refresh authorization or handle selection before trying again after a scope or permission refusal. |

A change handle reports the newest **observed committed version**. It can
coalesce commits, so use a durable work queue for actions that must run once
per commit. Use one consumer per change handle. Close it and its reader when
switching views or unmounting. The client can keep the prior view visible while
reconnecting, provided it distinguishes that state from current data.

## Watch commits directly

Use `Catalog.open_changes()` when you need to trigger a query yourself. Set
`include_initial=True` for a first version even when nothing has been written.
Keep a separate live reader and use `reader.at(change.version)` for a query
that must see **exactly** the delivered version, even if another commit is
already visible on the live handle.

```python
from gyldan_core import graph


def read_first_selection(catalog, database_id, handle_name, selection):
    with catalog.open_changes(
        database_id, handle=handle_name, include_initial=True, notify=False,
    ) as changes, catalog.open(database_id=database_id, read_only=True) as database:
        reader = database.get_handle(handle_name)
        change = changes.read_sync(timeout=2)
        if change is None:
            return None
        return graph.evaluate(reader.at(change.version), selection)
```

Filesystem activity can wake the monitor early. The periodic check remains
active, and `notify=False` selects polling alone. A direct read timeout returns
`None` and leaves the change handle open. Cancelling a pending direct async
read does not consume a pending version. If you cancel iteration of a query
watch, close the iterator and resume with your applied checkpoint. See the
[change-handle lifecycle](python-reference.md#change-handles-and-active-watches).
