import os
import iodata
import cmds

# Enkel test-runner
def run_test(name, func):
    try:
        func()
        print(f"[OK!] {name}")
    except Exception as e:
        print(f"[FAIL!] {name} -> {e}")


def setup():
    # Reset state
    iodata.DATABASES = {}
    iodata.LAST_RESULT = None

    # Mock data
    iodata.DATABASES["users"] = cmds.pd.DataFrame([
        {"name": "Alice", "age": 25},
        {"name": "Bob", "age": 32},
        {"name": "Charlie", "age": 29}
    ])


# -------------------
# TESTS
# -------------------

def test_select_all():
    cmds.execute_select("SELECT * FROM users")
    assert iodata.LAST_RESULT is not None


def test_select_where():
    cmds.execute_select("SELECT * FROM users WHERE age > 25")
    df = iodata.LAST_RESULT
    assert len(df) == 2
    

def test_select_order_by():
    cmds.execute_select("SELECT * FROM users ORDER BY age DESC")
    df = iodata.LAST_RESULT
    assert df.iloc[0]["age"] == 32


def test_select_limit():
    cmds.execute_select("SELECT * FROM users LIMIT 1")
    df = iodata.LAST_RESULT
    assert len(df) == 1


def test_delete():
    cmds.execute_delete("DELETE FROM users WHERE age < 30")
    df = iodata.DATABASES["users"]
    assert all(df["age"] >= 30)


def test_export_json():
    cmds.execute_select("SELECT * FROM users")
    iodata.execute_export_last("EXPORT LAST TO 'test.json'")
    assert os.path.exists("mockdata/test.json")
    os.remove("mockdata/test.json")


# Main, run all tests!

if __name__ == "__main__":
    print("Running tests...\n")

    setup()

    run_test("SELECT ALL", test_select_all)
    run_test("SELECT WHERE", test_select_where)
    run_test("SELECT ORDER BY", test_select_order_by)
    run_test("SELECT LIMIT", test_select_limit)
    run_test("DELETE", test_delete)
    run_test("EXPORT JSON", test_export_json)

    print("\nDone.")
