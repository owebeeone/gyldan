# Understand the basic ideas

Suppose your program needs to remember a collection of books. Each book has a
title and a page count. You want to save that information, find books that match
a condition, and inspect what changed over time.

Gyldan stores the information in files. Your program opens a session to work with
the database, then closes the session when it finishes. The saved data remains
available to the next session.

## Describe what a book contains

A **concept** describes a kind of object. In this example, `Book` is a concept.
Its **properties** are `title` and `pages`. Their types say what values are
accepted. A title holds text; a page count holds a number.

The collection of concepts and property definitions is the **schema**. You can
declare it in Python and apply it to the database. That lets Gyldan check writes
against the same definitions when the data is used again later.

A particular book is an **instance** of the Book concept. These snippets
illustrate reading and editing an existing book. The
[library tutorial](getting-started.md) shows how to create `book` and open the
`objects` handle used to edit it.

```python
book.title
book.pages
```

Each instance has a UUID. Its identity stays the same when a property changes,
and you can use that UUID to find it again after reopening the database.

## Save related edits together

A **transaction** groups changes. For example, changing a book's title and page
count can be one edit that succeeds together. A normal transaction exit commits
the edit. An exception leaving its body rolls it back.

```python
with objects.transaction():
    book.title = "Dune Messiah"
    book.pages = 256
```

Committing makes a new change in the handle's history. You can keep the earlier
version and ask Gyldan to read the object as it was at that point.

## Open a place to work

A **catalog** is a directory in which Gyldan can find databases. A database has
its own identity and can have a human-readable name such as `library`.

A **session** is one open connection to that stored database. The initial
**handle**, named `main`, selects the view your program works with. The Python
`ObjectHandle` adds typed object access over that handle.

For the first tutorial, use `main`. Later you can create child handles to work
on proposed changes separately. An overlay can read live parent data while
keeping its own values. A merge publishes selected child changes to its parent.

## Find saved objects

A **query** selects objects whose stored properties match a condition. The
library example finds books with at least 400 pages. Query results contain
objects from the selected handle view, so you can read their properties in the
same way as an object you created yourself.

The next steps are to [install Gyldan](installation.md) and
[create the library](getting-started.md). The tutorial includes complete code
for opening, editing, querying and reopening it.
