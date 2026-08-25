"""Seeds inventory.db with the starter schema exactly as given in the README.

Deliberately does NOT include SuperGizmo, MegaSprocket, or WidgetC - their
absence is intentional and is what lets the validation stage flag them as
unknown items.
"""

import sqlite3


def setup_db() -> None:
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)")
    cursor.execute("""
        INSERT OR IGNORE INTO inventory VALUES
        ('WidgetA', 15),
        ('WidgetB', 10),
        ('GadgetX', 5),
        ('FakeItem', 0)
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    setup_db()
    print("inventory.db seeded.")
