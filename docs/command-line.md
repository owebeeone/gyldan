# Command-line interface

The `gyldan` wheel installs `gyldan-shared`. You can also invoke it with
`python -m gyldan_shared`. Global options go before the command.

Follow the [installation steps](installation.md), then run the commands on
this page in order in the same shell, from a directory without `cli-data`.
On Windows, use a local NTFS directory. Save the JSON files as UTF-8 without
a byte-order mark.

```sh
gyldan-shared --help
gyldan-shared define --help
```

Each database command opens and closes its own session and writes JSON to
standard output on success. Errors go to standard error and return a nonzero
exit code.

## Create and inspect a catalog

```sh
gyldan-shared --catalog ./cli-data create library
gyldan-shared --catalog ./cli-data databases
gyldan-shared --catalog ./cli-data --database library info
```

`--catalog` selects a filesystem location. `--database` selects the stored
database name. The default handle is `main`; `--handle` selects another root
label or an existing child UUID.

`create` accepts `--bplus-node-size N` and `--radix-node-size N`. Each size
must be at least `2`; the defaults are `8` and `64`. The root keeps these
sizes for its lifetime. See [tree node sizes](storage-and-recovery.md#tree-node-sizes).

## Define a concept

Save the following as `book-schema.json` in the working directory.

```json
{
  "title": {"property_type": "string", "required": true},
  "pages": "number",
  "catalog_number": "bigint"
}
```

```sh
gyldan-shared --catalog ./cli-data --database library define Book --properties-file book-schema.json
```

A type-name shorthand declares an optional property. The supported type names
are `string`, `number`, `bigint`, `boolean`, `null`, `concept_instance` and
`unknown`.

## Add and read records

Save this as `book.json` in the same directory.

```json
{
  "title": "Dune",
  "pages": 412,
  "catalog_number": {"$bigint": "1267650600228229401496703205376"}
}
```

Add the record and save its UUID in `book_id` for the remaining commands.
The `add` result includes the new record's `id` and the acknowledged `change`.

=== "PowerShell"

    ```powershell
    $added = gyldan-shared --catalog ./cli-data --database library add Book --file book.json
    $added
    $book_id = ($added | ConvertFrom-Json).id
    ```

=== "Bash or Zsh"

    ```sh
    added=$(gyldan-shared --catalog ./cli-data --database library add Book --file book.json)
    printf '%s\n' "$added"
    book_id=$(printf '%s\n' "$added" | python -c 'import json, sys; print(json.load(sys.stdin)["id"])')
    ```

```sh
gyldan-shared --catalog ./cli-data --database library list Book --limit 10
gyldan-shared --catalog ./cli-data --database library concepts
gyldan-shared --catalog ./cli-data --database library show "$book_id"
```

The book has `pages` set to `412`. Its `catalog_number` comes back as a
`$bigint` object with the original decimal string.

## Update a record and read its history

Save this as `book-update.json` in the same directory.

```json
{"pages": 500}
```

```sh
gyldan-shared --catalog ./cli-data --database library set "$book_id" --file book-update.json
gyldan-shared --catalog ./cli-data --database library show "$book_id"
gyldan-shared --catalog ./cli-data --database library versions
gyldan-shared --catalog ./cli-data --database library show "$book_id" --at previous
```

The current record has `500` pages. `--at previous` reads the record with
`412` pages, since the preceding change on this handle was `add`. After other
commits, pass the change number from `versions` that you want to read. That
version must contain the record.

Each modifying command uses one transaction. `set` changes only the supplied
fields. To remove the optional `pages` value, run these commands. The final
`show` returns the same record with `pages` omitted.

```sh
gyldan-shared --catalog ./cli-data --database library remove-property "$book_id" pages
gyldan-shared --catalog ./cli-data --database library show "$book_id"
```

## Value representation

| JSON | Gyldan value |
| --- | --- |
| `"Dune"` | String |
| `412` or `1.5` | Number |
| `true` or `false` | Boolean |
| `null` | Explicit null |
| `{"$bigint": "12345678901234567890"}` | Bigint |
| `{"$ref": "instance-uuid"}` | Reference |
| `{"$ref": null}` | Targetless reference |

The record-oriented API uses signed 64-bit integer numbers for bare JSON
integers. Use `$bigint` for arbitrary-size integers. Returned records contain
`id`, `concept`, scalar `properties` and `keyed` entries.

## Commands at a glance

| Purpose | Commands |
| --- | --- |
| Database selection | `create`, `databases`, `info` |
| Schema | `concepts`, `define` |
| Records | `add`, `list`, `show`, `set`, `remove-property` |
| History | `versions`, `--at` on read commands |
| Folders | `folders-install`, `folder-create`, `folder-add`, `folder-remove` |

Use a command's `--help` for all its arguments and input alternatives. See
[operations and errors](operations.md) for creation capabilities and commit
failures.
