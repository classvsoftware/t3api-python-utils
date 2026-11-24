# Prompts and pickers

Scripts that a person runs in a terminal often need to ask something: which
license, which package, how much, and "submit this?". The library's prompts
cover that and match the look of its own pickers. Use them instead of
`input()`.

| Function | Asks for | Returns |
|---|---|---|
| `t3.confirm(question, *, default=False)` | yes or no | `bool` |
| `t3.ask(question, *, default=None, parse=None)` | a value | `str`, or what `parse` returns |
| `t3.choose(title, items, columns, render, *, filterable=None)` | one item from a numbered table | the item |
| `client.pick_license()` | one of the credential's licenses | the license number |
| `client.pick_endpoint(kind="collection")` | an endpoint from the spec | an `Endpoint` |
| `t3.pick_file(directory=".", *, patterns=...)` | a CSV, TSV, JSON or JSON Lines file | a `Path` |

## Without a terminal

All of them raise `t3.NotInteractive` when there's no terminal (or Jupyter
kernel) to ask in, for example in a scheduled job or CI. They never wait for
input that can't arrive. `input()` would raise `EOFError` or hang instead.

Ctrl-C raises `KeyboardInterrupt` to your script. The library never exits for
you.

So every interactive script needs a way to run without asking. The usual
pattern is a flag or an environment variable that supplies the answer:

```python
license = args.license or client.license or client.pick_license()
```

## confirm()

```python
if not t3.confirm(f"Create {len(items)} items in {license}?"):
    return
```

The default answer is **no**: pressing Enter declines. Pass `default=True` for
questions where yes is the safe answer.

To confirm before a bulk write, `bulk(submit="ask")` already shows the
validation results and asks. See
[Asking before submitting](writes.md#asking-before-submitting).

## ask()

```python
from datetime import date

name = t3.ask("Item name")
quantity = t3.ask("Quantity", parse=float)
when = t3.ask("Date (YYYY-MM-DD)", default=date.today().isoformat(), parse=date.fromisoformat)
```

An empty answer takes `default`, or asks again when there isn't one. `parse`
turns the text into something else. When it raises `ValueError`, the message is
shown in red and the question is asked again, so `parse=float` and
`parse=date.fromisoformat` need no extra checking. Any other exception from
`parse` propagates.

## choose()

`choose()` shows a list of anything as a numbered table:

```python
package = t3.choose(
    "Source package",
    packages,
    columns=["Label", "Item", "Quantity"],
    render=lambda p: [p["label"], p["item"]["name"], f'{p["quantity"]} {p["unitOfMeasureAbbreviation"]}'],
)
```

`render(item)` returns one string per column. The person types a number, or,
when the list is filterable, some text to narrow it down. `filterable` defaults
to on for more than 10 items. The table shows 40 rows at a time. An empty list
raises `ValueError`.

`pick_license()`, `pick_endpoint()` and `pick_file()` are built on it.
`pick_license()` returns at once, without asking, when the account has only
one license.
