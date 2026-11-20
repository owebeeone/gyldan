# Organize objects with folders

The `gyldan.folders` add-on supplies ordinary concepts and helper functions for
grouping database objects. You can use it when your application needs named
collections such as a Reading shelf and a Favorites shelf.

A folder contains references to objects. Adding a book to a folder keeps its
existing UUID and stored properties. The same book can belong to several folders.
These folders live inside the database; they are separate from the filesystem
directory that contains the database files.

## Install the folder schema

First run [your first database](getting-started.md) to create `./library-data`.
In the same working directory, copy this page's Python blocks into `shelves.py`
in order and then run the file once against that fresh library.

```python
from gyldan import ObjectHandle, folders, instance_id, query
from gyldan_shared import Catalog

database = Catalog("./library-data").open(name="library")
objects = ObjectHandle(database.get_handle("main"))
folders.install_folders(objects)
```

Call the installation helper outside an application transaction because it
manages its own schema transactions. It creates `FolderEntry` and `Folder` when
both are absent, or uses the concepts already present. A partially installed
pair requires attention before continuing.

`FolderEntry` provides an optional `name`. `Folder` inherits it and adds an
`entries` map of references to FolderEntry instances. Your own concept becomes
eligible for membership by inheriting from `FolderEntry`.

## Let books belong to folders

```python
with objects.transaction():
    folders.allow_in_folders(objects.get_concept("Book"))
```

After this schema change, retrieve objects through the current view before
using the folder helpers.

```python
books = query(objects.get_class("Book"))
book = books.where(books.title == "Dune").first()
book_id = instance_id(book)
with objects.transaction():
    reading = objects.create("Folder", name="Reading")
    favorites = objects.create("Folder", name="Favorites")
    folders.add(reading, book)
    folders.add(favorites, book)
```

The concept inheritance check ensures that entries support the expected
FolderEntry relationship. A property named `name` on an unrelated concept is
insufficient on its own.

## Read and change membership

```python
print(folders.contains(reading, book))  # True
print([entry.title for entry in folders.entries(reading)])  # ['Dune']
print(sorted(folder.name for folder in folders.folders_of(book)))
# ['Favorites', 'Reading']

with objects.transaction():
    folders.remove(reading, book)
print(folders.contains(reading, book), folders.contains(favorites, book))
# False True
print(objects.get(book_id).title)  # Dune
```

Membership edits need a transaction. Adding an existing membership has the same
final value. Removing an absent membership raises an error. Removing a book from
one folder leaves its memberships in other folders available.

## Folders can contain folders

```python
with objects.transaction():
    later = objects.create("Folder", name="Later")
    folders.add(reading, later)
    folders.add(later, book)

for entry in folders.walk(reading):
    print(type(entry).__name__)  # Folder, then Book

database.close()
```

Run the complete example from your working directory.

```sh
python shelves.py
```

Membership forms a graph, so cycles are possible. `walk` tracks UUIDs and yields
each reachable entry once. To repeat a traversal over the same data, capture a
version and obtain the folder from that fixed view.

All objects passed to these helpers belong to the same `ObjectHandle` view.
Rebind them by UUID when working with [another layer](handles-and-overlays.md).

The [CLI](command-line.md) provides `folders-install`, `folder-create`,
`folder-add` and `folder-remove` for the same stored relationships.
