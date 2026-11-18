"""Sample tables shared by the tests.

They are kept in a module of their own (not in conftest.py) so that tests can
import them without relying on how pytest names the conftest module.
"""

PEOPLE = [
    {"id": 1, "name": "Alice", "age": 25, "city": "Gdańsk", "score": 4.5, "note": "vip"},
    {"id": 2, "name": "Bob", "age": 32, "city": "Sopot", "score": 3.0, "note": None},
    {"id": 3, "name": "Charlie", "age": 29, "city": "Gdynia", "score": 2.5, "note": "new"},
    {"id": 4, "name": "Dana", "age": None, "city": "Gdańsk", "score": 5.0, "note": "vip"},
    {"id": 5, "name": "Eve", "age": 41, "city": "Sopot", "score": None, "note": None},
    {"id": 6, "name": "Frank", "age": 18, "city": "Kraków", "score": 1.5, "note": "old"},
]

CODES = [
    {"id": 1, "code": "10"},
    {"id": 2, "code": "20"},
    {"id": 3, "code": "x"},
]

ORDERS = [
    {"id": 1, "day": "2024-12-31", "amount": 10.5},
    {"id": 2, "day": "2025-01-15", "amount": 99.0},
    {"id": 3, "day": "2025-03-02", "amount": 5.25},
]
