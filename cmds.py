# cmds.py
# Functions for queries

import re
import pandas as pd
import iodata


# Helper functions for parsing SQL-based commands.
def getquery(query, keyword): # query = full string, keyword = command to extract
    if keyword not in query: # If none of the defined keywords are included, it returns nothing
        return None

    start = query.index(keyword) + len(keyword)
    rest = query[start:]

    stop_words = ["WHERE", "ORDER BY", "LIMIT"]

    end = len(rest)
    for word in stop_words:
        idx = rest.find(word)
        if idx != -1 and idx < end:
            end = idx

    return rest[:end].strip()


def get_table_name(query, keyword):  # query = full string, keyword = command to extract
    part = getquery(query, keyword)
    if not part:
        return None
    return part.split()[0].strip().lower()

# WHERE and BETWEEN
def normalize_where(where):
    if not where:
        return where

    # BETWEEN >= AND <=; Note: This is the least stable part of the code. Be careful when modifying here. LLM is helpful.
    between = re.search(r"(\w+)\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)", where, re.IGNORECASE)
    if between:
        col, low, high = between.groups()
        where = f"({col} >= {low}) AND ({col} <= {high})"

    where = where.replace(" AND ", " & ").replace(" OR ", " | ")
    where = where.replace(" = ", " == ") # These two rows could also use placeholders for additional safety

    return where


def safe_query(df, condition): # Executes a Pandas Dataframe query safely.
# If the condition is invalid, it prints an error and returns the unfiltered DataFrame instead of crashing.
    try:
        return df.query(condition)
    except Exception as e:
        print(f"[ERROR] WHERE failed: {e}")
        return df


# SELECT
def execute_select(query):
    try: # Using try is necessary to avoid crashing
        table = get_table_name(query, "FROM")

        if table not in iodata.DATABASES: # Make sure the directory is correct; standard is /mockdata/
            print(f"[ERROR] Table '{table}' not found")
            return

        df = iodata.DATABASES[table].copy() # Making a copy to avoid modifying the original data

        select_part = query[6:query.index("FROM")].strip()

        columns = list(df.columns) if select_part == "*" else [c.strip() for c in select_part.split(",")]
        
        ########
        # WHERE
        if "WHERE" in query: # If crashing, check WHERE
            where_part = normalize_where(getquery(query, "WHERE"))
            df = safe_query(df, where_part)
            
        # ORDER BY
        if "ORDER BY" in query:
            order = getquery(query, "ORDER BY").split()
            col = order[0] # Sorting by column x
            asc = not (len(order) > 1 and order[1] == "DESC") # Ascending is standard

            if col in df.columns:
                df = df.sort_values(by=col, ascending=asc)

        # LIMIT
        if "LIMIT" in query:
            try:
                limit = int(getquery(query, "LIMIT"))
                df = df.head(limit) # Head the most logical to use; tail also possible but quickly gets funny
            except:
                print("[ERROR] Invalid LIMIT")

        df = df[columns]

        iodata.LAST_RESULT = df.copy() # Saving copy for use later

        print(df.to_string(index=False))

    except Exception as e:
        print(f"[CRASH] SELECT failed: {e}")


# DELETE
def execute_delete(query):
    try:
        table = get_table_name(query, "FROM") # Get name of table to delete

        if table not in iodata.DATABASES:
            print(f"[ERROR] Table '{table}' not found")
            return

        df = iodata.DATABASES[table]

        if "WHERE" in query: # If crashing, check WHERE!
            where = normalize_where(getquery(query, "WHERE"))
            to_delete = safe_query(df, where).index
        else:
            to_delete = df.index # Removes all if no row numbers given

        iodata.DATABASES[table] = df.drop(to_delete).reset_index(drop=True) # Drop; removing rows and resets

        print(f"[OK] Deleted {len(to_delete)} rows")

    except Exception as e:
        print(f"[CRASH] DELETE failed: {e}")
