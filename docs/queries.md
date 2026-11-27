# Find objects with queries

A query finds instances of a concept in one handle view. In the library example,
you might want every book with at least 400 pages, or a book with a particular
title. The result contains the same generated Python objects you use elsewhere.

Run [concepts and objects](concepts-and-objects.md) first to create `./concepts-data`
with its book, author and note. In the same working directory, copy this page's
Python blocks into `find_books.py` in order. Run the file once after adding the
last block. The final example edits the book's page count.

## Start with a generated class

```python
from gyldan import ObjectHandle, query
from gyldan_shared import Catalog

database = Catalog("./concepts-data").open(name="library")
objects = ObjectHandle(database.get_handle("main"))
Book = objects.get_class("Book")
books = query(Book)
for book in books:
    print(book.title, book.pages)  # Dune 412
```

The class comes from the selected `ObjectHandle`, after its schema has committed.
The query uses that class's concept and view. Obtain a class from a historical
or child handle to query that view instead.

## Add a condition

```python
long_books = books.where(books.pages >= 400)
titles = [book.title for book in long_books]
dune = books.where(books.title == "Dune").first()
print(titles)  # ['Dune']
print(dune.title)  # Dune
```

Iteration runs the query. `first()` returns one matching object or `None`. Each
execution answers from the selected view when that execution starts. A query
object can be executed again after the live view has changed.

## Order the results

```python
by_length = books.order_by(books.pages.desc(), books.title.asc())
longest = by_length.where(books.pages.exists()).first()
print(longest.title)  # Dune
```

The query compares terms left to right and uses ascending record UUID to
break ties. `asc()` and `desc()` both put missing values last by default.
Pass `missing="first"` to either method to put them first. An absent field,
a stored null or a NaN counts as missing for ordering. An object attribute's
schema default only participates if its value is stored in the query view.

Use concrete scalar text, boolean or numeric fields. Each term must come
from the query's class and view. Use item access for a field whose Python
name collides with a query method, such as `books["order_by"].asc()`.
Calling `order_by()` with zero terms restores listing order. Calling
`where()` before or after ordering preserves the requested order.

Ordering can examine every candidate before returning the first result.
Use a fixed view for repeated executions that must see the same version.

## Combine conditions

```python
matching = books.where((books.pages >= 400) & (books.title == "Dune"))
alternatives = books.where((books.title == "Dune") | (books.title == "Emma"))
other_titles = books.where(~(books.title == "Dune"))
print([book.title for book in matching])  # ['Dune']
print([book.title for book in alternatives])  # ['Dune']
print([book.title for book in other_titles])  # []
```

Use parentheses around comparisons, and combine them with `&`, `|` and `~`.
Python's `and`, `or` and `not` ask for an immediate truth value. Gyldan needs to
retain the condition so the database can evaluate it for each instance.

Conditions in one query must belong to the same generated class and view.
Rebuild the query terms when changing views.

## Values, ranges and absence

| Expression | Selects |
| --- | --- |
| `books.title == "Dune"` | A stored title equal to the string |
| `books.pages >= 400` | A stored page count at least 400 |
| `books.pages.between(200, 500)` | A stored page count from 200 through 500, including both bounds |
| `books.title.is_in(["Dune", "Emma"])` | A stored title equal to one of those values |
| `books.pages.exists()` | An instance with a stored page count |
| `books.pages.missing()` | An instance with no stored page count |

An object's schema default can supply a value when you read its attribute.
Query matching uses the stored field. Use `missing()` when looking for an
absent stored value, even if a default appears on ordinary reads.

## Collections and references

The `Note` example in [concepts and objects](concepts-and-objects.md#lists-maps-and-defaults)
has a `tags` list and a `ratings` map.

```python
notes = query(objects.get_class("Note"))
tagged = notes.where(notes.tags.contains("reading"))
rated = notes.where(notes.ratings.has_key("interest"))
highly_rated = notes.where(notes.ratings["interest"] >= 4)
first_tag = notes.where(notes.tags[0] == "reading")

for results in (tagged, rated, highly_rated, first_tag):
    print([note.title for note in results])  # ['Untitled']
```

`contains` checks whether any entry has the supplied value. `has_key` checks for
one entry, and indexing selects the entry to compare. List indices are integer
positions. Map keys retain their Gyldan types.

Compare a reference property with an object obtained from the same view:

```python
people = query(objects.get_class("Person"))
author = people.where(people.name == "Frank Herbert").first()
by_author = books.where(books.author == author)
print([book.title for book in by_author])  # ['Dune']
```

This example uses the `Book.author` schema from the concepts guide. Use the
author's UUID to look it up in a different view before building a query there.

## Pending edits and historical queries

An object query inside an active transaction flushes pending object edits before
it reads. That lets the query reflect what the transaction is about to commit.
A refusal during that flush is an error in the transaction and needs the same
handling as another write.

```python
original_version = objects.get_version()
with objects.transaction():
    dune.pages = 300

old_objects = objects.at(original_version)
old_books = query(old_objects.get_class("Book"))
print([book.title for book in old_books.where(old_books.pages >= 400)])  # ['Dune']
print([book.title for book in books.where(books.pages >= 400)])  # []

database.close()
```

Run the complete example from your working directory.

```sh
python find_books.py
```

Current query execution scans the selected concept's records. Large result sets
and retained historical views have memory and storage costs. See
[storage and history costs](storage-and-recovery.md#history-memory-and-storage-growth)
when planning long-running workloads.

For reference traversal, parameterized lenses and live updates after commits,
see [graph queries and change notifications](graph-queries-and-watches.md).
