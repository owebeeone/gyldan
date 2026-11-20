# Your first database

This walkthrough creates a small library, changes a book, reads its earlier
state and reopens the saved data. Run it in a new working directory after
[installing Gyldan](installation.md).

Copy the Python blocks below into `first_library.py` in order. Run the file
after adding the last block.

On Windows, choose a local NTFS location for the catalog in this walkthrough.
The [operations guide](operations.md#filesystem-creation-support) explains the
explicit best-effort option for ReFS.

## Define the schema

A concept describes the properties of its instances. A decorated Python class
declares the schema that Gyldan applies inside a transaction.

```python
from gyldan import ObjectHandle, concept, concept_property, instance_id, query
from gyldan_shared import Catalog


@concept
class Book:
    title: str = concept_property(required=True)
    pages: float
```

`str` declares text. `float` declares a number property, which also accepts
ordinary integer values. An `int` annotation declares an arbitrary-size bigint.

## Create and edit objects

```python
catalog = Catalog("./library-data")

with catalog.create("library") as database:
    objects = ObjectHandle(database.get_handle("main"))
    with objects.transaction():
        objects.define(Book)

    with objects.transaction():
        book = objects.create("Book", title="Dune", pages=412)
    book_id = instance_id(book)
    original = objects.get_version()

    with objects.transaction():
        book.pages = 500

    books = query(objects.get_class("Book"))
    print([item.title for item in books.where(books.pages >= 400)])
    print(objects.at(original).get(book_id).pages)  # 412
    print(book.pages)                              # 500
```

The query prints `['Dune']`. The next two lines show the earlier and current
page counts.

A successful transaction context commits its changes. An exception in the body
rolls them back. Schema changes commit before you create instances of their
generated classes.

`create("library")` creates a new database. A name collision raises an error.
Use `open(name="library")` for subsequent sessions.

## Reopen the database

```python
with catalog.open(name="library") as database:
    objects = ObjectHandle(database.get_handle("main"))
    reopened = objects.get(book_id)
    print(reopened.title, reopened.pages)  # Dune 500
    print(objects.at(original).get(book_id).pages)  # 412
```

Keep instance UUIDs when you need to find the same objects in a later session.
Obtain fresh wrappers from the new `ObjectHandle`; closing a session invalidates
its objects and handles. The `original` version above is retained in this
program so the reopened session can select the same historical view.

You can inspect available databases with the catalog:

```python
for info in catalog.databases():
    print(info.name, info.database_id, info.problems)
```

Run the walkthrough from your working directory.

```sh
python first_library.py
```

The last line lists `library`, its generated database UUID and its catalog
problems. The successful listing has no problems.

Save the complete [library example](examples/library.py) as `library.py` in your
working directory to also try rollback. Give it a separate, fresh catalog path.

```sh
python library.py ./example-data
```

The script prints `Created` with the database UUID and `Reopened` with the book
UUID and `Dune 500`.

Continue with [concepts and objects](concepts-and-objects.md) or
[transactions and history](transactions-and-history.md).
