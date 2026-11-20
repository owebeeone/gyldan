# Handles and overlays

The root handle is named `main`. A child handle gives you a separate place to
commit changes while retaining access to its parent data.

## A handle selects a view over layers

A layer holds its own committed changes. A handle selects that layer and its
visible parent ancestry. If the child has its own value for a property, that
value takes precedence. Otherwise the view can read the inherited value. The
same book UUID can therefore have different visible page counts in two handles.

This lets an application try a revision without immediately publishing that
revision to the parent. Layers also have a physical cost because each native
child has its own journal and working files. See
[storage and recovery](storage-and-recovery.md).

## Choose a child mode

| Mode | Parent data seen by the child |
| --- | --- |
| `HandleEnum.COW` | The parent's captured state when the child was created |
| `HandleEnum.OVERLAY` | Live parent state between transactions, with child values taking precedence |

A transaction pins its starting view. Fixed and historical views retain their
captured coordinates. The current native provider supports a single parent per
child.

Consider a book whose parent value is initially 412 pages:

| Operation | Root | Overlay | COW child |
| --- | ---: | ---: | ---: |
| Create both children | 412 | 412 | 412 |
| Parent commits 500 | 500 | 500 | 412 |
| Overlay commits 700 | 500 | 700 | 412 |
| Merge the overlay page count | 700 | 700 | 412 |

The COW child's inherited data stays at the creation view. The overlay follows
later parent changes until it has its own value for the same property. A
transaction in either child keeps the ancestry it captured when it began.

## Create an overlay

After [installing Gyldan](installation.md), paste the next two blocks in order
into `overlays.py` in a fresh working directory. On Windows, use a local NTFS
location for the catalog. The example uses Core handles for child creation and
merge and wraps them in `ObjectHandle` for typed object editing.

```python
from gyldan import ObjectHandle, concept, instance_id
from gyldan_core import HandleEnum
from gyldan_shared import Catalog


@concept
class Book:
    pages: float


database = Catalog("./overlay-data").create("library")
root = database.get_handle("main")
objects = ObjectHandle(root)
with objects.transaction():
    objects.define(Book)
with objects.transaction():
    book = objects.create("Book", pages=412)
book_id = instance_id(book)

child = root.create_handle(HandleEnum.OVERLAY)
child_objects = ObjectHandle(child)
child_book = child_objects.get(book_id)
cow = root.create_handle(HandleEnum.COW)
cow_objects = ObjectHandle(cow)
cow_book = cow_objects.get(book_id)

print(book.pages, child_book.pages, cow_book.pages)  # 412 412 412
with objects.transaction():
    book.pages = 500
print(book.pages, child_book.pages, cow_book.pages)  # 500 500 412
with child_objects.transaction():
    child_book.pages = 700
print(book.pages, child_book.pages, cow_book.pages)  # 500 700 412
```

The overlay reads its own `pages` value. The root continues to read its parent
value until a merge publishes the selected change there. Each handle has its
own local change numbers.

Use `HandleEnum.COW` to make a child whose inherited data stays at the captured
parent state. Obtain objects through the child's wrapper so references and
generated classes belong to that view.

## Merge selected properties

```python
from gyldan_core import PropertyKey

change = child.merge_to_parent({PropertyKey(book_id, "pages", None)})
print(book.pages, child_book.pages, cow_book.pages)  # 700 700 412
database.close()
```

Run the complete example from your working directory.

```sh
python overlays.py
```

The third part of `PropertyKey` selects a keyed entry. `None` selects a scalar
property. A merge commits to the parent and returns its change number. The
parent's schema and value rules validate the proposed result. Perform it after
ending the relevant transactions.

`child.merge()` merges all the child's changes. Choose a property selection
when only part of the work is ready to publish. Merging keeps the child handle
and its history available.

## Keep identities and versions

Record UUIDs identify instances across compatible views and reopened sessions.
A generated wrapper belongs to its current `ObjectHandle`. Rebind by UUID when
moving between views.

For a consistent multi-step read, capture a version and use the corresponding
fixed view. An overlay's local change number alone does not describe all of its
live parent coordinates. See [transactions and history](transactions-and-history.md).
