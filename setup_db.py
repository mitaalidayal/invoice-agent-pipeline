"""Seeds inventory.db with the starter schema from the README, extended with
unit_price (for price validation) and an approved_vendors table (for vendor
validation) - both above-and-beyond additions the README explicitly invites
("consider adding tables for those as well").

Deliberately does NOT include SuperGizmo, MegaSprocket, or WidgetC in
inventory, or 'Fraudster LLC' in approved_vendors - their absence is
intentional, letting Validation flag unknown items/vendors.

Drops and recreates both tables on every run, rather than CREATE IF NOT
EXISTS + INSERT OR IGNORE, so the schema can evolve (like this unit_price
addition) without anyone needing to manually delete a stale inventory.db
first - it always fully re-seeds instead of silently working against an old
2-column table.
"""

import sqlite3


def setup_db() -> None:
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS inventory")
    cursor.execute("CREATE TABLE inventory (item TEXT PRIMARY KEY, stock INTEGER, unit_price REAL)")
    cursor.execute("""
        INSERT INTO inventory VALUES
        ('WidgetA', 15, 250.00),
        ('WidgetB', 10, 500.00),
        ('GadgetX', 5, 750.00),
        ('FakeItem', 0, 1000.00)
    """)

    cursor.execute("DROP TABLE IF EXISTS approved_vendors")
    cursor.execute("CREATE TABLE approved_vendors (vendor TEXT PRIMARY KEY)")
    cursor.execute("""
        INSERT INTO approved_vendors VALUES
        ('Widgets Inc.'),
        ('Gadgets Co.'),
        ('Precision Parts Ltd.'),
        ('Global Supply Chain Partners'),
        ('Acme Industrial Supplies'),
        ('MegaWidgets Corp'),
        ('NoProd Industries'),
        ('Consolidated Materials Group'),
        ('Summit Manufacturing Co.'),
        ('QuickShip Distributers'),
        ('Atlas Industrial Supply'),
        ('TechParts International'),
        ('Reliable Components Inc.')
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    setup_db()
    print("inventory.db seeded.")
