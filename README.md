

# SQLatmask v0.2.0

A lightweight SQL-like query engine built in Python using Pandas.
SQLatmask allows you to execute simplified SQL commands directly on JSON-based tables through a command-line interface (CLI).
It can be used both as a learning tool for practicing SQL and as a lightweight solution for querying data stored in JSON files.


## SQL Query in Sway

Example of executing a SQL query in a terminal within my Sway (Wayland) desktop environment:
![SQL Query Result](img/img01.png)


## Features

- SELECT queries with column filtering, column aliases (`name AS customer`) and `DISTINCT`
- WHERE clause with:
	- `=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`
	- `AND`, `OR`, `NOT` and parentheses, with the usual SQL precedence
	- `BETWEEN ... AND ...` for whole numbers, decimals, negative numbers and text
	- `IN (...)`
	- `LIKE` with `%` and `_` wildcards
	- `IS NULL` / `IS NOT NULL`
- ORDER BY on several columns (`ORDER BY city ASC, age DESC`)
- LIMIT and OFFSET
- DELETE with a required WHERE clause, or `DELETE ALL FROM <table>` when you really mean it
- EXPORT LAST TO, with overwrite protection
- JSON‑based storage (`mockdata/xxxx.json`), written atomically
- Command‑line interface: interactive, one-shot (`-c`) or scripted (`--file`)
- Queries are not case sensitive, and keywords inside quoted values are left alone


## Example Queries

- SELECT * FROM customers;

- SELECT name, age FROM customers WHERE age BETWEEN 20 AND 30;

- SELECT * FROM customers ORDER BY age DESC;

- SELECT city FROM customers WHERE city LIKE 'East%' LIMIT 10 OFFSET 5;

- SELECT DISTINCT city FROM customers;

- SELECT name AS customer FROM customers WHERE city IN ('San Jose', 'Phoenix');

- DELETE FROM customers WHERE age < 20;

The same statements work from the shell:

```
python main.py -c "SELECT name, age FROM customers WHERE age > 60 ORDER BY age DESC"
python main.py --file queries.sql
```

and from Python:

```python
from sqlatmask import cmds, iodata

iodata.load_json_files("mockdata")
rows = cmds.execute_select("SELECT name FROM customers WHERE age > 60")
```


## How It Works

Tables are stored as .json files inside the mockdata/ directory (loaded at startup)
Data is loaded into pandas DataFrames at runtime
Queries are tokenised and parsed into a small syntax tree (`sqlatmask/queryparser.py`)
WHERE conditions are evaluated directly on the DataFrame (`sqlatmask/where.py`), not turned into a `DataFrame.query()` string


## Project Structure

```
├── main.py                  # thin wrapper so `python main.py` keeps working
├── sqlatmask/
│   ├── cli.py               # argument parsing, command loop, batch mode
│   ├── cmds.py              # SELECT and DELETE execution
│   ├── iodata.py            # load/save/export JSON tables
│   ├── queryparser.py       # tokenizer, statement parser, syntax tree
│   ├── where.py             # WHERE evaluation against a DataFrame
│   └── shelp.py             # help banner
├── tests/                   # pytest suite
├── TESTALL.py               # the original hand-rolled test runner
├── mockdata/                # JSON data storage
└── pyproject.toml
```


## Getting Started

1. Install dependencies

```
pip install pandas
```

or install the package itself (this also gives you the `sqlatmask` command):

```
pip install .
```

2. Run the program

```
python main.py
```

or

```
python -m sqlatmask
```


## Example Output

SQL> SELECT * FROM customers WHERE age BETWEEN 24 AND 27;

```
 name   age
Alice    25
  Bob    26
(2 rows)
```


## Limitations

- No JOIN support
- No aggregate functions (COUNT, SUM, AVG, ...) and no GROUP BY
- INSERT and UPDATE removed in this version until proven stable
- Values keep the type they have in the JSON file: comparing a number column with a quoted value is reported as an error instead of being silently coerced
- LIKE is case insensitive (as in SQLite); `where.LIKE_CASE_SENSITIVE` switches it to exact case


## Design Notes

This project started as a simple keyword-based query experiment and quickly evolved toward a more SQL-like project.

Pandas was chosen as the underlying engine because its DataFrame model naturally uses tabular data and already supports operations like filtering, sorting, and querying.
This made it possible to focus on translating SQL-like input rather than implementing a full execution layer from scratch.

The first versions cut statements apart with string indexes and handed the WHERE clause to `DataFrame.query()`.
That was small, but every mistake had the same shape: a condition that could not be understood was treated as "no condition at all", so a SELECT quietly returned the whole table and a DELETE quietly removed every row.

The current version tokenises the input (quotes included), parses it into a small syntax tree, and evaluates conditions against the data itself.
Anything that cannot be parsed or answered raises a `QueryError` naming the column, the value or the clause at fault, and the statement does not run.


## Tests

```
python -m pytest          # 140 tests
python TESTALL.py         # the original six-check runner, still supported
```


## Future Plans

- Support for INSERT, UPDATE, MERGE, JOIN etc.
- Aggregate functions and GROUP BY
- NULL-aware comparisons (`IS DISTINCT FROM`)
- More CLI conveniences (`--format csv`, piping results)


## What I Learned

- Using pandas as a query engine, although it wasn't all that necessary for other than training reasons.
- Pandas has got fantastic documentation easily found.
- Writing a tokenizer makes error messages possible: a parser knows *where* the problem is, a chain of `str.replace` calls never does.


## License

MIT


## Author

Matias Back
https://github.com/framstu
