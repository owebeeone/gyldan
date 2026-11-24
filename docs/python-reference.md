# Python API reference

This reference covers the public methods used in the user guide. Start with
[your first database](getting-started.md) for a complete program.

## Catalog and sessions

Import `Catalog` from `gyldan_shared`.

| Call | Result |
| --- | --- |
| `Catalog(path)` | A catalog at a filesystem path |
| `catalog.create(name, **options)` | A new writable native database session |
| `catalog.open(name=..., database_id=..., root_journal=..., read_only=False, **options)` | A session for an existing database; supply at most one selector |
| `catalog.databases()` | Catalog entries with names, UUIDs, root-journal names and reported problems |
| `database.database_id()` | The persisted database UUID |
| `database.get_handle(name="main")` | A Core handle in this session |
| `database.transaction_outcome(handle_uuid, transaction_uuid)` | An outcome with `status` and optional `change_number` |
| `database.close()` | Close this session and its resources |

Both `catalog.create` and `catalog.open` support context-manager use. Creation
options include `segment_size`, `log_level`, `log_directory` and
`directory_durability`. Opening supports `log_level` and `log_directory`.

## ObjectHandle

Import `ObjectHandle`, `instance_id`, `concept` and `concept_property` from
`gyldan`.

| Call | Result |
| --- | --- |
| `ObjectHandle(core_handle)` | An object view over a Core handle |
| `objects.transaction()` | A transaction context that commits on normal exit |
| `objects.define(declaration, name=None)` | Apply a schema declaration inside a transaction |
| `objects.create(concept, **properties)` | Create an instance inside a transaction |
| `objects.get(instance_uuid)` | An object from this view |
| `objects.get_concept(name)` | The concept's schema object |
| `objects.get_class(concept)` | The generated class for a committed concept |
| `objects.get_version()` | This view's complete version |
| `objects.at(version)` | A fixed object view at that version |
| `objects.create_handle(mode)` | An object view for a new child handle |
| `instance_id(object)` | The object's UUID |

`concept` names a concept by string in the examples. `define` accepts an optional
keyword-only `name`. The transaction object returned by `with` exposes
`change_number` after a successful exit.

## Declarations

```python
from gyldan import concept, concept_property


@concept
class Book:
    title: str = concept_property(required=True)
    pages: float
```

`@concept(name="Name", parents=("Parent",))` can supply a name and existing
parent concepts. Decorated class inheritance also declares concept inheritance.
`concept_property(required=False, validator=None)` supplies field metadata.
See [concepts and objects](concepts-and-objects.md) for supported annotations and
schema reconciliation.

## Queries

After running the [concepts and objects](concepts-and-objects.md) example, open
its catalog from the same working directory. Pass a generated class bound to the
desired view to `query`.

```python
from gyldan import ObjectHandle, query
from gyldan_shared import Catalog

with Catalog("./concepts-data").open(name="library", read_only=True) as database:
    objects = ObjectHandle(database.get_handle("main"))
    books = query(objects.get_class("Book"))
    matching = books.where((books.pages >= 300) & (books.title == "Dune"))
    for book in matching:
        print(book.title)  # Dune
```

Iterating `matching` yields objects. `matching.first()` returns the first match
or `None` when there is no match. Combine conditions with `&` and `|`, using
parentheses around the component expressions.

## Graph selections and change notifications

These APIs are available in current alpha development builds. See
[Graph queries and change notifications](graph-queries-and-watches.md) for a
runnable example.

| Call | Result |
| --- | --- |
| `graph.Selection(rules, summaries=...)` | Named rules and an optional mapping from concept names to summary field names |
| `graph.Rule(name, set, detail=Detail.FULL)` | A named set expression with full, summary or reference detail |
| `graph.evaluate(handle, selection, params=None, *, reference=False)` | A `SelectionResult` with a version and records keyed by UUID |
| `graph.evaluate_tracked(handle, selection, params=None, *, reference=False)` | A result and the state required by `advance` |
| `graph.advance(handle, tracked, to_version=None)` | A new tracked result and the delta, targeting the live version by default |
| `catalog.open_changes(database_id, *, handle="main", include_initial=False, interval=1.0, notify=True)` | A `ChangeHandle` for committed view changes |
| `graph.watch_selection(changes, handle, selection, params=None, *, since=None)` | An async iterator over `SelectionDelta` values |

Import `graph` from `gyldan_core` and `Catalog` from `gyldan_shared`.
Use `Detail.FULL`, `Detail.SUMMARY` or `Detail.REF` from `graph`. Result records
carry `concept`, `detail`, `values`, `changes` and `rules`. `values` maps field
names to Core property values. `changes` contains the record's latest available
change coordinates per layer. `REF` records carry identity and rule membership
with no values or change coordinates. Each delta has `from_version`,
`to_version`, `added`, `removed` and `updated`.

Keep a live Core reader on the same database and handle as the change handle
for the duration of a query watch. Use context managers to close the database
session and change handle, and `contextlib.aclosing` to end the watch when you
leave an async iteration early. `reference=True` selects the provider-neutral
evaluator for evaluation and tracking.

For direct observation, `changes.poll()`, `changes.read_sync(timeout=None)`
and `await changes.read(timeout=None)` return a `Change` with
`database_id`, `handle_uuid`, `version` and `initial`. Polling with no pending
change and reads that time out return `None`. Only one read may be pending per
change handle. A read returns the newest observed view, which may include
multiple commits. Closing the change handle ends iteration and wakes pending
direct reads.

## Core handles and layers

Import `HandleEnum` and `PropertyKey` from `gyldan_core`.

| Call | Result |
| --- | --- |
| `handle.get_version()` | A complete `Version` with handle-local ancestry coordinates |
| `handle.at(change_number)` or `handle.at(version)` | A fixed historical Core handle |
| `handle.create_handle(HandleEnum.COW)` | A child with captured parent ancestry |
| `handle.create_handle(HandleEnum.OVERLAY)` | A child with live parent ancestry between transactions |
| `handle.merge()` | Merge all child changes to its parent and return the parent's change number |
| `handle.merge_to_parent({PropertyKey(instance_uuid, property_name, key)})` | Merge selected scalar properties or keyed entries |

Use `key=None` for a scalar property. Child creation and merge are lifecycle
operations performed outside the relevant transactions. See
[handles and overlays](handles-and-overlays.md) for an end-to-end selection.
