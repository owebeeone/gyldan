# Concepts and objects

Schema is ordinary Gyldan data. The built-in `concept` and `property` concepts
describe your application concepts and their fields. The object API creates
Python wrapper classes from committed schema.

After [installing Gyldan](installation.md), paste the Python blocks on this page
in order into `concepts.py` in a fresh working directory. On Windows, use a
local NTFS location for the catalog. The script leaves `concepts-data`
available for the [query walkthrough](queries.md).

## Declare concepts in Python

```python
from gyldan import ObjectHandle, concept, concept_property
from gyldan_core.validation import value
from gyldan_shared import Catalog


@concept
class Person:
    name: str = concept_property(required=True)


@concept
class Book:
    title: str = concept_property(required=True)
    pages: float = concept_property(validator=value >= 0)
    catalog_number: int
    author: Person | None
```

Create a database and apply both concepts in one schema transaction, with the
referenced `Person` first.

```python
database = Catalog("./concepts-data").create("library")
objects = ObjectHandle(database.get_handle("main"))

with objects.transaction():
    objects.define(Person)
    objects.define(Book)

with objects.transaction():
    author = objects.create("Person", name="Frank Herbert")
    book = objects.create(
        "Book", title="Dune", pages=412, catalog_number=1 << 100, author=author,
    )
print(book.author.name)  # Frank Herbert
```

The declaration class supplies schema metadata. Create instances through
`objects.create`, and obtain the generated class with
`objects.get_class("Book")` after the schema commits.

| Annotation | Stored property type |
| --- | --- |
| `str` | `string` |
| `float` | `number` |
| `int` | `bigint` |
| `bool` | `boolean` |
| A decorated concept class | A reference targeting that concept |

Fields are optional unless `concept_property(required=True)` declares a new
required field. `T | None` can express an optional annotation. Required metadata
is controlled by `concept_property`. Validators use rules from
`gyldan_core.validation`.

Reapplying a decorated declaration reconciles its own fields. An unchanged
declaration makes no schema writes. Omitting a previously declared field
detaches that field from the concept. Existing values must support a requested
type change. Review the full declaration when applying a schema update.

## Inheritance

Subclass a decorated concept to declare inheritance, or name an existing parent.
Install the folder schema to make `FolderEntry` available before applying
`Article`.

```python
from gyldan import folders


@concept
class IllustratedBook(Book):
    illustrator: str


@concept(parents=("FolderEntry",))
class Article:
    title: str


folders.install_folders(objects)
with objects.transaction():
    objects.define(IllustratedBook)
    objects.define(Article)

IllustratedBookObject = objects.get_class("IllustratedBook")
ArticleObject = objects.get_class("Article")
print(issubclass(IllustratedBookObject, objects.get_class("Book")))  # True
print(issubclass(ArticleObject, objects.get_class("FolderEntry")))  # True
```

Instances of a derived concept can be used where the parent is required.

## Lists, maps and defaults

Use ordinary schema objects for collection shapes and default values. This
example defines a separate `Note` concept:

```python
with objects.transaction():
    note = objects.create("concept", name="Note")
    note.properties["title"] = objects.create(
        "property", name="title", property_type="string", required=False,
        default="Untitled",
    )
    note.properties["tags"] = objects.create(
        "property", name="tags", property_type="string", required=False,
        shape="list",
    )
    note.properties["ratings"] = objects.create(
        "property", name="ratings", property_type="number", required=False,
        shape="map",
    )

with objects.transaction():
    item = objects.create("Note", tags=["reading"], ratings={"interest": 5})
    item.tags.append("history")
    item.ratings["interest"] = 4
print(item.title)  # Untitled
print(list(item.tags), item.ratings["interest"])  # ['reading', 'history'] 4
```

Collection edits need a transaction, including in-place changes to lists and
maps. Outside a writable transaction, collection readings are immutable.

For maps that distinguish keys such as `True`, `1` and `1.0`, construct a
`gyldan.KeyMap` from pairs. A Python dictionary combines those equal keys before
Gyldan receives it.

## Queries

```python
from gyldan import query

books = query(objects.get_class("Book"))
matching = books.where((books.pages >= 400) & (books.title == "Dune"))
print([book.title for book in matching])  # ['Dune']
print(matching.first().title)  # Dune
database.close()
```

Run the complete example from your working directory.

```sh
python concepts.py
```

Queries evaluate stored values in the selected handle view. Object queries in
a transaction flush pending object edits before evaluation. A schema default
supplies an object read value; an absent stored field remains absent for query
matching. Current execution scans records, so pagination and conditions do not
promise index performance.
