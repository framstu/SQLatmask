# shelp.py
# Combined header and help shown when opening or typing 'HELP'

def showhelp():
    print(" ")
    print("""
====  SQLatmask v0.1.0  ====

Examples:
 SELECT * FROM users;
 SELECT * FROM users WHERE age BETWEEN 20 AND 30;
 SELECT * FROM users ORDER BY age DESC;
 EXPORT LAST TO 'users_filtered.json'; (requires SELECT first)
 SHOW TABLES;
 DESCRIBE users;
 EXIT

Valid commands:
 SELECT, DELETE, SHOW TABLES, DESCRIBE, EXIT
 HELP to show this header again!
 
 Using UPPERCASE in queries is required!
    """)
