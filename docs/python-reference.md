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

These APIs are available in current alpha development builds. Import
`graph` from `gyldan_core` and `Catalog` from `gyldan_shared`. Use a
Core handle from the provider. See the
[lens examples and UI update guide](graph-queries-and-watches.md).

### Operators

| Expression | Meaning |
| --- | --- |
| `graph.Param(name)` | A named parameter supplied in `params`. Its value is one record UUID or a reusable iterable of UUIDs, such as a tuple. Use it alone or inside `Ids`. |
| `graph.Ids(items=())` | Seed from a tuple of record UUIDs and parameters. |
| `graph.Scan(concept, where=None)` | Select the named concept and its derived instances, optionally using a Core `Condition`. |
| `graph.Step(property, direction=Direction.OUT, concept=None, where=None)` | Follow a scalar reference forward by default. For `Direction.IN`, name the concept whose records point back through the property. `where` filters reached records. |
| `graph.Follow(source, steps, min_repeat=1, max_repeat=1, include_source=False, fanout=None)` | Repeat a nonempty tuple of steps between the supplied bounds. `max_repeat=None` stops when no new records are reached. `include_source` includes the starting records. `fanout` keeps up to that many reached UUIDs per source in identity order. |
| `graph.Union(parts)`, `graph.Intersect(parts)`, `graph.Except(left, right)` | Combine set expressions by union, intersection or difference. |
| `graph.Where(source, predicate)` | Keep records matching a Core `Condition`, `Exists` or `Compare`. The same predicate forms work on `Step.where`. |
| `graph.Exists(steps, negate=False)` | Test whether a path reaches any record. Use `negate=True` to test absence. |
| `graph.Compare(left, right, equal=True)` | Compare the identity sets reached by two paths. Use `equal=False` to test inequality. |
| `graph.Rule(name, set, detail=Detail.FULL)` | Give a set expression a unique rule name and a projection level. |
| `graph.Selection(rules, summaries=...)` | A tuple of named rules with an optional mapping from concept names to tuples of summary field names. |

Null or missing references contribute no outward target. An inward step
without a concept raises `NotAcceptable("inward_step_needs_concept")`.
Invalid repeat bounds or empty steps raise `invalid_follow`. A fanout below
one raises `invalid_fanout`. Duplicate rule names raise `duplicate_rule`.
A missing parameter is an error. The Reference evaluator reports
`NotThere("parameter")`. Start a new tracked evaluation or watch to change
parameter values.
Use bounded traversals for interactive queries and sort rows separately for
display. Fanout is a result limit, so the evaluator can still have to
traverse or scan more records before applying it.

### Evaluation, tracked changes and results

| Call | Result |
| --- | --- |
| `graph.evaluate_set(handle, node, params=None)` | A set of UUIDs selected by one expression through the provider-neutral evaluator, including on Native Shared. |
| `graph.evaluate(handle, selection, params=None, *, reference=False)` | A `SelectionResult` with `version` and `records` keyed by UUID. |
| `graph.delta(handle, selection, from_version, to_version, params=None, *, reference=False)` | A `SelectionDelta` obtained by evaluating both historical views in full. |
| `graph.evaluate_tracked(handle, selection, params=None, *, reference=False)` | A `Tracked` result with selection, parameters, result and read dependencies. |
| `graph.advance(handle, tracked, to_version=None)` | An `Advance` result at the supplied version or the live version by default. Keep its new `tracked` state for the next call. |
| `graph.changes_between(handle, from_version, to_version)` | The written `PropertyKey` slots and created record UUIDs across visible layers in the range. |
| `graph.touched_slots(handle, from_version, to_version)` | Only the written slots from `changes_between`. |

`reference=True` uses the provider-neutral evaluator for that call. Native
Shared captures one view for its default C++ selection evaluator. The
provider-neutral path reads the supplied view repeatedly. For a coherent
committed result while other sessions can write, pass a fixed Core view to
`evaluate_set`, `evaluate` or `evaluate_tracked`. For example, use
`graph.evaluate_tracked(reader.at(reader.get_version()), selection, params)`
with a committed reader. If a change notification supplies the version, use
`reader.at(change.version)`. Advance forward on the same database, handle
ancestry, selection and parameters.

Each delivered `Record` has `concept` (the concept UUID), `detail`,
`values`, `changes` and `rules`. `values` maps field names to Core
`PropertyValue` instances. `changes` contains the latest available record
change per layer, in view order. `rules` lists the rules that reached the
record in selection order. `Detail.FULL` projects available keyless values
from the record's defined fields. `Detail.SUMMARY` projects available keyless
values for the fields configured for the record's actual concept, so supply
a summary for each derived concept that needs fields in the result.
`Detail.REF` carries identity, concept and rule membership and leaves
`values` and `changes` empty.

Keyed list and map entries are outside both field projections. A change to
one of those entries can still update a selected record's `changes`.
To read the `tags` collection for a selected Note at `result.version`, pin the
same Core reader to that version and fetch each tagged key.

```python
note = reader.at(result.version).get_instance(note_id)
tags = {
    key: note.get_keyed_property("tags", key).value
    for key in note.get_property_keys("tags")
}
```

A delta has `from_version`, `to_version`, `added` and `updated` maps keyed
by UUID, and a `removed` set of UUIDs. A change to the detail, values,
record change metadata or reaching rules can produce an update. Removal
means leaving the selection. A record that leaves one rule and still
matches another remains in the result with updated rule membership.

`Advance` holds `delta`, `tracked`, `affected` and `work`. The
`affected` flag describes whether the change met the dependencies. Check
the delta itself for changes to deliver. Native `work` reports the counts
for nodes evaluated, nodes reused, projections evaluated and projections
reused, in that order. Reference advance returns `None` for `work`.

### Change handles and active watches

| Call | Result or lifetime |
| --- | --- |
| `catalog.open_changes(database_id, *, handle="main", include_initial=False, interval=1.0, notify=True)` | Open an independent consumer of committed view changes. Supply a database UUID and handle label. `interval` is in seconds. `notify=False` uses polling alone. |
| `changes.poll()` | Return the newest ready `Change`, or `None` immediately. |
| `changes.read_sync(timeout=None)`, `await changes.read(timeout=None)` | Wait for a `Change`. A timeout in seconds returns `None`. Omission waits until a change or closure. |
| `changes.open_reader()` | In Shared, return a Core handle that retains its own read-only session. The returned handle has a lifetime independent of the change handle, and this call exposes no public session context. A change handle without a reader factory raises `NotAcceptable("no_reader")`. |
| `changes.close()`, `changes.closed` | End the handle and check whether it is closed. Synchronous and asynchronous context managers close it on exit. |
| `graph.watch_selection(changes, handle, selection, params=None, *, since=None)` | Async iterator of `SelectionDelta` values. Supply a live Core reader for the same database and resolved handle. With `since`, use the last applied complete `Version` for that selection and parameter set. |

A `Change` carries `database_id`, `handle_uuid`, `version` and `initial`.
It can represent several commits. Reading it advances that change handle's
position. Each independent consumer needs its own handle. A concurrent
poll or read on the same handle raises
`NotAcceptable("change_handle_busy")`. Cancelling an async direct read
before settlement leaves its position unchanged. If cancellation races
with delivery, the version may already have advanced. Open a new change
handle with `include_initial=True` and query its exact version to recover
without another commit. Closing the change handle ends iteration and wakes
pending direct reads with
`NotThere("change_handle_closed")`.

Use `reader.at(change.version)` for an exact delivered view. The live reader
can have advanced by the time you query. A watch yields a full initial
snapshot without `since`, and with `since` it yields only changes to the
selection. An unchanged catch-up leaves the iterator waiting for an update.
The watch advances past commits with empty deltas internally, so the next
emitted `from_version` can differ from the last delivered `to_version`.
At startup or resume, the reader can be ahead of the observation. Compare
complete ordered versions before applying a patch. Ignore duplicate or
older targets with the same ancestry and request a snapshot for
incompatible ancestry.

Use `contextlib.aclosing` to close the iterator on early exit. For
deterministic reader cleanup, use `with catalog.open(database_id=...,
read_only=True) as database` and obtain the Core reader from
`database.get_handle(...)`. Manage the change handle in its own context.
Shared's `CoreHandle.close()` is a write-side handle operation and raises
`NotAllowed("read_only")` on a read-only reader. On reconnect, resume from
the last applied checkpoint for the same verified authorization and query
scope. Request a full snapshot if that scope changes or history is
unavailable.

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
