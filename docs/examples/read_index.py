"""Watch the read index work on a fresh native catalog.

Usage: python read_index.py /path/to/fresh-catalog
Requires an installed gyldan wheel and supported native creation.
The database is retained after the example; rerunning the same name refuses it.
"""
import argparse
from pathlib import Path


def moved(before, after, *names):
    return {name: after[name] - before[name] for name in names}


def read_books(handle, books):
    return [handle.record(book)["properties"]["pages"] for book in books]


def main(path):
    from gyldan_shared import Catalog

    catalog = Catalog(path)

    with catalog.create("library") as database:
        database_id = database.database_id()
        handle = database.get_handle("main")

        # The index is built in and on unless the engine was compiled without it.
        state = database.read_index_statistics()
        assert state["built"] is True and state["enabled"] is True

        with handle.transaction():
            handle.define_concept("Book", {
                "title": {"property_type": "string", "required": True},
                "pages": "number",
            })
        with handle.transaction():
            books = [handle.create_record("Book", {"title": title, "pages": pages})
                     for title, pages in (("Dune", 412), ("Emma", 474), ("Ulysses", 730))]

        # The first read of a value fetches it from storage and keeps it.
        before = database.read_index_statistics()
        assert read_books(handle, books) == [412, 474, 730]
        first = database.read_index_statistics()
        assert first["fetches"] > before["fetches"]

        # Reading the same values again is served from the index.
        assert read_books(handle, books) == [412, 474, 730]
        again = database.read_index_statistics()
        repeat = moved(first, again, "hits", "fetches", "derived_hits")
        assert repeat["hits"] > 0 and repeat["fetches"] == 0
        print("Repeated read:", repeat)

        # A commit is absorbed on the next read. It does not empty the index:
        # only the value the commit rewrote is fetched again.
        with handle.transaction():
            handle.set(books[0], "pages", 500)
        assert read_books(handle, books) == [500, 474, 730]
        after_commit = database.read_index_statistics()
        commit = moved(again, after_commit, "absorbed_changes", "restarts", "hits")
        assert commit["absorbed_changes"] >= 1 and commit["restarts"] == 0
        assert commit["hits"] > 0
        print("After a commit:", commit)

        # Switched off, every read goes to storage and returns the same values.
        database.set_read_index(False)
        off = database.read_index_statistics()
        assert off["enabled"] is False
        assert read_books(handle, books) == [500, 474, 730]
        direct = moved(off, database.read_index_statistics(), "hits", "bypass_switched_off")
        assert direct["hits"] == 0 and direct["bypass_switched_off"] > 0
        print("Switched off:", direct)

        # Switched on again, it starts empty and fills as values are read.
        database.set_read_index(True)
        assert database.read_index_statistics()["enabled"] is True
        assert read_books(handle, books) == [500, 474, 730]
        assert read_books(handle, books) == [500, 474, 730]
        assert database.read_index_statistics()["hits"] > off["hits"]

        print("Database:", database_id)

    # A reopened database has a new, empty index that is on again.
    with catalog.open(database_id=database_id, read_only=True) as database:
        state = database.read_index_statistics()
        assert state["enabled"] is True and state["hits"] == 0
        assert read_books(database.get_handle("main"), books) == [500, 474, 730]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="A fresh directory for the example catalog")
    main(parser.parse_args().path)
