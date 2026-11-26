# Read index

Each open database keeps a read index in process memory. It remembers what
reads of committed data found, and the schema facts worked out from them, so
that repeated reads do not go back to storage. It is on by default and needs
no configuration.

Use this page to check that the index is working, to measure what it is doing,
or to rule it out when diagnosing a problem.

The examples below run in order against a fresh catalog directory. The
[runnable version](examples/read_index.py) contains the complete flow with
its checks:

```sh
python read_index.py /path/to/fresh-catalog
```

## What it does and does not do

- It never changes what a read returns. A read answered from the index returns
  what the same read of storage returns.
- It is never written to disk and is not shared between processes. Each open
  database in each process has its own, and it is gone when the database is
  closed.
- A commit adds to it. It does not have to be rebuilt after a transaction, in
  this process or another.
- Reads inside an open transaction see that transaction's own pending writes
  first, as they always have. Pending writes are never kept in the index.
- It applies to property reads, key listings, concept listings, schema lookups
  and the queries built on them.

It does not speed up history calls, such as an instance's history or a tracked
graph selection's first evaluation. Those read each change's stored lists and
are not served by the index.

## Check that it is on

Create a small database to read from. The index is on as soon as the database
is open.

```python
from gyldan_shared import Catalog

catalog = Catalog("./read-index-data")

with catalog.create("library") as database:
    state = database.read_index_statistics()
    print(state["built"], state["enabled"])

    handle = database.get_handle("main")
    with handle.transaction():
        handle.define_concept("Book", {
            "title": {"property_type": "string", "required": True},
            "pages": "number",
        })
    with handle.transaction():
        books = [handle.create_record("Book", {"title": title, "pages": pages})
                 for title, pages in (("Dune", 412), ("Emma", 474), ("Ulysses", 730))]
```

Both values are `True` in the published wheels.

## Read the counters

`read_index_statistics()` returns a dictionary of counts since the database
was opened. Take it before and after the work you want to measure and
subtract.

```python
def pages(handle):
    return [handle.record(book)["properties"]["pages"] for book in books]

with catalog.open(name="library") as database:
    handle = database.get_handle("main")

    start = database.read_index_statistics()
    assert pages(handle) == [412, 474, 730]      # fetched from storage and kept
    first = database.read_index_statistics()
    assert pages(handle) == [412, 474, 730]      # served from the index
    again = database.read_index_statistics()

    print("first read fetched", first["fetches"] - start["fetches"])
    print("repeat read fetched", again["fetches"] - first["fetches"],
          "and was served", again["hits"] - first["hits"])
    assert again["fetches"] == first["fetches"] and again["hits"] > first["hits"]

    with handle.transaction():
        handle.set(books[0], "pages", 500)
    assert pages(handle) == [500, 474, 730]
    after = database.read_index_statistics()
    print("changes absorbed", after["absorbed_changes"] - again["absorbed_changes"],
          "restarts", after["restarts"] - again["restarts"])
    assert after["restarts"] == again["restarts"]
```

A commit is absorbed on the next read. It does not empty the index: only the
value the commit rewrote is fetched again.

| Entry | Meaning |
| --- | --- |
| `built` | Whether the engine was built with the index. `True` in the published wheels. |
| `enabled` | Whether this open database's index is on. |
| `hits` | Values served from the index. |
| `fetches` | Values read from storage and then kept. |
| `derived_hits` | Schema facts served from the index. |
| `derived_computed` | Schema facts worked out and then kept. |
| `absorbed_changes` | Committed transactions the index has caught up on. |
| `history_fetches` | Times a read fetched change lists in order to catch up. |
| `restarts` | Times one handle's index dropped what it held and started again. |
| `value_drops` | Times one handle's index shed its kept values at its bound. |
| `bypass_switched_off` | Reads that went to storage because the index is off. |
| `bypass_no_stamp` | Reads of a view layer that is not entitled to use the index. |
| `bypass_older_stamp` | Reads through a view captured before the handle's history was reloaded. |
| `bypass_below_range` | Reads of a version older than the index covers. |
| `bypass_catching_up` | Reads that went to storage while the index could not catch up. |

What to expect:

- The first read of a value is a fetch. Reading it again is a hit.
- After a commit, `absorbed_changes` rises on the next read. Values the commit
  did not touch are still hits.
- A historical view older than the first one read through the index counts
  under `bypass_below_range`. It is correct and reads storage directly.
- `restarts` should stay at or near zero in ordinary use. A steadily rising
  count means the index is being emptied repeatedly and is worth reporting.
- `value_drops` rises only when one handle's index holds more than about a
  million kept values. The values are read again on demand.

## Switch it off and on

```python
with catalog.open(name="library") as database:
    handle = database.get_handle("main")
    indexed = pages(handle)

    database.set_read_index(False)               # every read now goes to storage
    off = database.read_index_statistics()
    assert off["enabled"] is False
    assert pages(handle) == indexed
    assert database.read_index_statistics()["hits"] == off["hits"]

    database.set_read_index(True)                # starts empty again
    assert database.read_index_statistics()["enabled"] is True
    assert pages(handle) == indexed
```

`set_read_index` takes a `bool` and affects that open database only.
Switching off drops everything the index holds, so switching it back on starts
empty. Use it to compare timings, or to confirm that a result does not depend
on the index. If a read returns something different with the index off, that
is a defect: please report it with the counters from both runs.

## Memory

The index grows with what is read and with what is committed while the
database is open. It is bounded per handle by a count of kept values and a
count of change marks, and per database by a count of schema states. At a
bound it sheds entries and reads them again when asked. These bounds are not
configurable from Python.

See the [Python reference](python-reference.md#catalog-and-sessions) for the
two methods.
