"""Create, edit and reopen a small Gyldan library in a fresh catalog."""

import argparse
from pathlib import Path

from gyldan import ObjectHandle, concept, concept_property, instance_id, query
from gyldan_shared import Catalog


@concept
class Book:
    title: str = concept_property(required=True)
    pages: float


def main(directory):
    catalog = Catalog(directory)
    with catalog.create("library") as database:
        identity = database.database_id()
        objects = ObjectHandle(database.get_handle("main"))
        with objects.transaction():
            objects.define(Book)
        with objects.transaction():
            book = objects.create("Book", title="Dune", pages=412)
        book_id = instance_id(book)
        original = objects.get_version()
        with objects.transaction():
            book.pages = 500

        try:
            with objects.transaction():
                book.title = "Temporary title"
                raise ValueError("cancel this edit")
        except ValueError:
            pass
        assert book.title == "Dune"
        assert objects.at(original).get(book_id).pages == 412

        books = query(objects.get_class("Book"))
        assert [item.title for item in books.where(books.pages >= 400)] == ["Dune"]
        print("Created", identity)

    with catalog.open(name="library") as database:
        objects = ObjectHandle(database.get_handle("main"))
        book = objects.get(book_id)
        assert (book.title, book.pages) == ("Dune", 500)
        assert objects.at(original).get(book_id).pages == 412
        print("Reopened", instance_id(book), book.title, book.pages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="fresh catalog location")
    main(parser.parse_args().directory)
