# iodata.py
# Functions for loading, importing, saving and exporting tables into .JSON files

import os # For interacting with the file system
import json # Enables utilizing the .JSON format
import pandas as pd

DATABASES = {} # Empty dictionary for tables loaded
LAST_RESULT = None # Placeholder for latest query
DATA = "mockdata" # The directory used for loading and saving data

# Loading tables on startup
def load_json_files():
    if not os.path.exists(DATA):
        os.makedirs(DATA)
        print(f"[INFO] Created directory: {DATA}") # If needed, creating directory {DATA}, or 'mockdata' defined earlier

    for filename in os.listdir(DATA):
        if filename.endswith(".json"): # Only reading .json files!
            path = os.path.join(DATA, filename)
            table_name = filename[:-5]

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                DATABASES[table_name] = pd.DataFrame(data)
                print(f"[OK] Loaded: {table_name}")

            except Exception as e:
                print(f"[ERROR] Failed loading {filename}: {e}")

# Saving data, function for .json only
def save_json_files():
    for table, df in DATABASES.items():
        path = os.path.join(DATA, f"{table}.json")
        try:
            df.to_json(path, orient="records", indent=2)
        except Exception as e:
            print(f"[ERROR] Failed saving {table}: {e}")

# Showing / listing tables
def show_tables():
    print("\nTables:")
    for name in DATABASES:
        print(f" - {name}")

# Describing table
def describe_table(table):
    if table not in DATABASES:
        print(f"[ERROR] Table '{table}' not found")
        return

    print(DATABASES[table].dtypes)

# Export function; when exporting, exports the last results
def execute_export_last(query):
    global LAST_RESULT

    if LAST_RESULT is None:
        print("[ERROR] No previous result to export") # Exporting results requires the user to engage with the data first
        return

    try:
        parts = query.split()

        if len(parts) < 4 or parts[1] != "LAST" or parts[2] != "TO":
            print("[ERROR] Use: EXPORT LAST TO 'filename.json'")
            return

        # Extract filename from command
        filename = parts[3].strip("'\"")

        # Ensure mockdata folder exists
        folder = "mockdata"
        os.makedirs(folder, exist_ok=True)

        # Build full path
        filepath = os.path.join(folder, filename)

        df = LAST_RESULT

        # Overwrite check
        if os.path.exists(filepath):
            confirm = input("File already exists. Overwrite? (Y/N): ").upper()
            if confirm != "Y": # Overwrite negative by standard, may be changed to == "N" if validation used after
                return

        # Export based on extension; validating and exporting
        if filepath.endswith(".json"):
            df.to_json(filepath, orient="records", indent=2)
        else:
            print("[ERROR] Use .json")
            return

        print(f"[OK] Exported to {filepath}") # Exported to database directory, standard is /mockdata/

    except Exception as e:
        print(f"[ERROR] EXPORT failed: {e}")
