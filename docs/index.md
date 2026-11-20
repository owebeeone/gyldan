# Gyldan

GyldanDB saves application data in a local database and keeps its change history.
You describe the kinds of data your program needs, create objects, and commit
related edits together. Later, you can reopen those objects or read an earlier
version.

This guide builds a small library of books. It starts with one book's title and
page count, then adds queries, history and separate views for proposed edits.
You need basic Python familiarity to follow the Python examples.

After [installing](installation.md) the `gyldan` distribution, you can run these
imports in Python to load the object API and the file-backed catalog.

```python
from gyldan import ObjectHandle, concept, concept_property
from gyldan_shared import Catalog
```

## Start here

1. [Understand the basic ideas](understanding-gyldan.md) through the library example.
2. [Install Gyldan](installation.md) in a Python virtual environment.
3. [Create your first database](getting-started.md) and reopen its objects.
4. [Define concepts and properties](concepts-and-objects.md) for your data.
5. [Use transactions and history](transactions-and-history.md) to edit and read
   earlier states.

## Work with a database

- [Handles and overlays](handles-and-overlays.md) explain isolated changes and
  merges.
- [Queries](queries.md) find objects by values, ranges, references and collections.
- [Folders](folders.md) add named groups of objects through an optional helper.
- [Storage and recovery](storage-and-recovery.md) explain journals, segments,
  interrupted transactions and the costs of retained history.
- [The command-line interface](command-line.md) creates, inspects and edits
  databases from scripts and terminals.
- [Operations and errors](operations.md) cover file locations, commit outcomes,
  stale sessions and diagnostics.
- [The library example](examples/library.py) demonstrates schema, objects,
  queries, rollback and reopening in one program.
- [The Python API reference](python-reference.md) lists the methods used in the
  guide, their inputs and their results.

## Alpha releases

Gyldan is in alpha. APIs, journals and storage formats can change between alpha
revisions. Keep the version used for a database with your application's release
information. The compatibility policy starts with the first actual minor
release. Version 1.0 starts its own compatibility line.

This guide documents the `0.0.0a2` Python package. Its code is assembled
from the component revisions recorded by this release repository.
