# shelp.py
# Combined header and help shown when opening or typing 'HELP'

HELP_TEXT = """
====  SQLatmask v0.2.0  ====

Examples:
 SELECT * FROM customers;
 SELECT name, age FROM customers WHERE age BETWEEN 20 AND 30 ORDER BY age DESC;
 SELECT city FROM customers WHERE city LIKE 'East%' LIMIT 10 OFFSET 5;
 SELECT DISTINCT city FROM customers;
 SELECT name AS customer FROM customers WHERE city IN ('San Jose', 'Phoenix');
 EXPORT LAST TO 'customers_filtered.json'; (requires SELECT first)
 SHOW TABLES;
 DESCRIBE customers;
 EXIT

Valid commands:
 SELECT [DISTINCT] <columns|*> FROM <table>
        [WHERE <condition>]
        [ORDER BY <column> [ASC|DESC] [, ...]]
        [LIMIT <n>] [OFFSET <n>]
 DELETE FROM <table> WHERE <condition>
 DELETE ALL FROM <table>          (deletes every row on purpose)
 EXPORT LAST TO '<file>.json' [OVERWRITE]
 SHOW TABLES, DESCRIBE <table>, HELP, EXIT

Conditions:
 age >= 30 / city = 'San Jose' / city != 'Phoenix'
 age BETWEEN 20 AND 30          (whole numbers, decimals and negatives)
 city IN ('San Jose', 'Phoenix')
 city LIKE 'East%'              ('%' is any text, '_' is one character)
 name IS NULL / name IS NOT NULL
 Combine them with AND, OR and NOT, and group them with parentheses.

Queries are not case sensitive: 'select' and 'SELECT' both work.
"""


def showhelp(*, out=print) -> None:
    out(HELP_TEXT)
