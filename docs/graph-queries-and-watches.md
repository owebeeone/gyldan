# Graph queries and change notifications

A graph selection describes the records a caller needs from one Core handle.
Named rules can start from identities or a concept scan, follow references,
filter records, and combine sets. Each rule requests full fields, a summary,
or a reference. Gyldan combines results by record UUID, keeping the highest
requested detail and all the rule names that reached the record. Graph
projections include keyless values. Read collection entries separately at the
[delivered version](python-reference.md#evaluation-tracked-changes-and-results).

An application can compile a saved lens into a selection. The application owns
the lens definition, authorization, display order, and delivery protocol. On
Native Shared, Gyldan evaluates selections in C++. A query watch advances a
tracked selection as the handle's committed view changes.

## Set up a development environment

The published `0.0.0a3` wheel provides `gyldan_core.graph` and
`Catalog.open_changes()`, so the Native Shared examples on this page run with
the installed `gyldan` package. The earlier `0.0.0a2` wheel predates them.

The first example uses the in-memory Reference provider, which is in the
separate `gyldan-test-py` package and is not part of the `gyldan` wheel. To
run it, install matching development builds from a complete sibling workspace.
The public release repository describes its matching wheel artifacts.
[Python release builds](https://github.com/owebeeone/gyldan#python-release-builds)

For a source install, use the following commands from the workspace root in
your active virtual environment. The first line includes the Reference package
required for the first example. Run the second line for the Native Shared
examples. Source builds of Validator and Native Shared require a C++ toolchain.
Native Shared uses C++23 and its sibling C++ dependencies.

```sh
python -m pip install ./gyldan-validator ./gyldan-core-py ./gyldan-python ./gyldan-test-py
python -m pip install ./gyldan-shared-py
```

Check that Python is using the intended build.

```sh
python -c "from gyldan_core import graph; from gyldan_testing import MemoryStorage"
python -c "from gyldan_shared import Catalog; assert hasattr(Catalog, 'open_changes')"
```

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
view = handle.at(handle.get_version())
assert graph.evaluate_set(view, linked_books) == {book_id}
first = graph.evaluate_tracked(view, selection, params)
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

The example needs a writable Native Shared catalog with an existing database
and handle whose schema defines a `Book` concept with a string `title`.
On a build and filesystem that support native creation, run the Python
blocks in [Concepts and objects](concepts-and-objects.md) in the development
environment above. This prepares `./concepts-data`, database `library`
and handle `main`. If creation is unavailable, use a catalog prepared with
the matching build and pass its path, database name and handle label to the
script.

The watch uses a live read-only session and a separate writer on that same
handle. It applies a snapshot and a live update, then catches up after a
write made while the watch is closed.

Save the three blocks below in order as `watch_books.py`. The checkpoint
contains both the applied rows and the complete ordered version. It lives
in a temporary directory for the demonstration. For recovery across process
restarts, use a persistent destination. Store both together before
acknowledging delivery. Key the checkpoint by verified authorization and
visibility scope as well as database, resolved handle, selection and
parameters. This local example uses one fixed scope.

```python
import asyncio
from contextlib import aclosing, asynccontextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from gyldan import ObjectHandle, instance_id
from gyldan_core import LayerChange, NotThere, Version, graph
from gyldan_shared import Catalog


def version_of(state):
    if state is None:
        return None
    return Version(tuple(LayerChange(*layer) for layer in state["layers"]))


class SnapshotRequired(Exception):
    pass


def at_or_before(earlier, later):
    return len(earlier.layers) == len(later.layers) and all(
        old.handle_uuid == new.handle_uuid and old.change_number <= new.change_number
        for old, new in zip(earlier.layers, later.layers)
    )


def apply_and_save(path, state, delta):
    if delta.from_version is None:
        rows = {}
    elif delta.from_version == version_of(state):
        rows = dict(state["rows"])
    else:
        raise SnapshotRequired("Delta has the wrong base")

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
    if delta.from_version is None:
        return apply_and_save(path, state, delta)
    base = version_of(state)
    if base is None:
        raise SnapshotRequired("No applied checkpoint")
    if at_or_before(delta.to_version, base):
        return state
    if not at_or_before(base, delta.to_version):
        raise SnapshotRequired("The target is not a forward view of this checkpoint")
    if delta.from_version != base:
        # Recover a strictly forward patch when the watch skipped an empty delta.
        try:
            delta = await asyncio.to_thread(
                graph.delta, reader, selection, base, delta.to_version
            )
        except NotThere as error:
            if error.reason == "version":
                raise SnapshotRequired("The checkpoint is unavailable") from error
            raise
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
@asynccontextmanager
async def open_book_watch(catalog, database_id, handle_name, selection, since=None):
    async with catalog.open_changes(database_id, handle=handle_name) as changes:
        with catalog.open(database_id=database_id, read_only=True) as database:
            reader = database.get_handle(handle_name)
            if changes.handle_uuid != reader.get_id():
                raise ValueError("The change handle and reader resolved different handles")
            async with aclosing(graph.watch_selection(
                changes, reader, selection, since=since,
            )) as watch:
                yield watch, reader


async def next_checkpoint(watch, checkpoint, state, reader, selection):
    while True:
        try:
            delta = await anext(watch)
        except NotThere as error:
            if error.reason == "version":
                raise SnapshotRequired("The watched version is unavailable") from error
            raise
        updated = await apply_watch_delta(checkpoint, state, delta, reader, selection)
        if updated is not state:
            return updated


async def watch_books(catalog, database_id, handle_name):
    selection = graph.Selection(
        (graph.Rule("books", graph.Scan("Book"), graph.Detail.SUMMARY),),
        summaries={"Book": ("title",), "IllustratedBook": ("title",)},
    )
    with TemporaryDirectory() as directory:
        checkpoint = Path(directory) / "books.json"
        async with open_book_watch(
            catalog, database_id, handle_name, selection,
        ) as (watch, reader):
            state = await next_checkpoint(watch, checkpoint, None, reader, selection)
            book_id = await asyncio.to_thread(
                write_book, catalog, database_id, handle_name, "Emma"
            )
            state = await asyncio.wait_for(
                next_checkpoint(watch, checkpoint, state, reader, selection), timeout=10,
            )
            assert state["rows"][book_id] == "Emma"

        # The original stream is closed and both old handles are released.
        await asyncio.to_thread(
            write_book, catalog, database_id, handle_name, "Emma (revised)", book_id
        )
        restored = json.loads(checkpoint.read_text(encoding="utf-8"))

        async def read_from(prior):
            async with open_book_watch(
                catalog, database_id, handle_name, selection, since=version_of(prior),
            ) as (watch, reader):
                return await asyncio.wait_for(
                    next_checkpoint(watch, checkpoint, prior, reader, selection), timeout=10,
                )

        try:
            state = await read_from(restored)
        except SnapshotRequired:
            state = await read_from(None)
        assert state["rows"][book_id] == "Emma (revised)"
```

```python
if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--catalog", default="./concepts-data")
    parser.add_argument("--database", default="library")
    parser.add_argument("--handle", default="main")
    args = parser.parse_args()
    catalog = Catalog(args.catalog)
    with catalog.open(name=args.database, read_only=True) as database:
        database_id = database.database_id()
    asyncio.run(watch_books(catalog, database_id, args.handle))
```

For an existing prepared catalog, run
`python watch_books.py --catalog PATH --database NAME --handle LABEL`.

A watch without `since` yields a full snapshot even if the selection is empty.
A resumed watch yields no immediate item if the result is unchanged. Multiple
commits can be coalesced, and an unrelated commit may yield no query delta.
The watch still advances internally, so the next nonempty delta can have a
`from_version` newer than the last delivered version. During startup or
resume, the live reader can also be ahead of a notification already observed
by the monitor. The example ignores equal or older targets with the same
ordered ancestry and bridges only a strictly forward gap. Recompute from the
applied checkpoint only within the same verified scope and while both
versions are available. If the versions are incompatible, retained history is
unavailable, or the receiver lacks the matching rows, reopen without `since`
and replace the view with a fresh snapshot. A new authorization or selection
scope starts with its own authorized snapshot.

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
| A new watch or a change of handle, filters, or parameters | Cancel the old subscription and reject late frames by subscription identity, including frames with the same data version. Replace all rows on the new snapshot, including an empty one. |
| One screen shows data from several handles | Keep a separate query and applied version for each handle. Combine the delivered rows in the application. |
| A patch arrives | Require an active scope, matching ordered ancestry and a forward target. Ignore duplicate or older targets in the same ancestry. Check the base, remove departed UUIDs, upsert added and updated rows, and re-sort. For a forward gap, recompute from a valid checkpoint or resnapshot. Incompatible ancestry needs a snapshot. |
| Provenance, permissions or edit metadata arrive separately | Apply them only to the matching scope and data version. Refresh edit tokens even when displayed fields are unchanged. |
| A transient disconnect leaves the same authorization valid | Back off before reconnecting. Reopen from the last applied checkpoint for that scope or request a new snapshot. You can mark the prior view stale while retrying. |
| Authorization changes, is no longer verifiable, or the server refuses the scope | Hide cached rows and provenance, retire the subscription, and invalidate its checkpoint for reuse. Discard buffered frames from the old subscription. Once the new scope is authorized, start with a fresh snapshot, even if the data version is unchanged. |

A change handle reports the newest **observed committed version**. It can
coalesce commits, so use a durable work queue for actions that must run once
per commit. Use one consumer per change handle. Close it and its reader when
switching views or unmounting.

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
`None` and leaves the change handle open. Cancellation before the async read
settles leaves its position unchanged. If cancellation races with delivery,
the handle may have recorded the version even though the caller received
only cancellation. To recover without waiting for another commit, close that
handle and use `read_first_selection` to open a new one with
`include_initial=True` and evaluate its exact observed version. If you cancel
iteration of a query watch, close the iterator and resume with your applied
checkpoint. See the
[change-handle lifecycle](python-reference.md#change-handles-and-active-watches).
