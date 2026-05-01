# main.py
# Main file containing the main function.

import iodata # Functions for loading, saving and exporting data to and from .JSON files. .CSV is also possible and has been used here, but I choose to focus on .JSON. 
import cmds # Functions for queries
import shelp # Header file, or HELP if you want


def main():
    iodata.load_json_files()
    shelp.showhelp()

    while True:
        query = input("\nSQL> ").strip().rstrip(";")

        if not query:
            continue

        if query == "EXIT": # For choosing between exiting and saving or only exiting
            choose = input("Save current table before exiting (Y) or (N)? ".upper() )
            if choose == "Y":
                iodata.save_json_files() # Save function from iodata.py, focusing on .json; Saving before exit!
                print("Table saved. Goodbye!")
            else:
                print("Goodbye!")
            break

        elif query == "SHOW TABLES": # Show tables loaded (successfully from /mockdata/)
            iodata.show_tables()

        elif query.startswith("DESCRIBE"): # Describe tables loaded
            table = query.split()[1].lower()
            iodata.describe_table(table)

        elif query.startswith("SELECT"): # Basic select
            cmds.execute_select(query)

        elif query.startswith("DELETE"): # Deleting data
            cmds.execute_delete(query)

        elif query.startswith("EXPORT LAST"): # Exporting the latest table
            iodata.execute_export_last(query)

        elif query == "HELP": # Simply showing the header with examples again
            shelp.showhelp()

        else:
            print("[ERROR] Unknown command. Type again or type HELP for commands.")


# Always loading the main function
if __name__ == "__main__":
    main()
