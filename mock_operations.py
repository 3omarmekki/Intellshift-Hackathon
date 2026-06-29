import sqlite3
import random
import pandas as pd
import numpy as np

DB = "superstore.db"

WAREHOUSES = [
    {"name": "West Coast Hub", "city": "Los Angeles", "state": "California", "region": "West",
     "capacity": 10000, "staff": 45, "queue": 120},
    {"name": "East Coast Hub", "city": "New York", "state": "New York", "region": "East",
     "capacity": 12000, "staff": 55, "queue": 200},
    {"name": "Central Distribution", "city": "Chicago", "state": "Illinois", "region": "Central",
     "capacity": 8000, "staff": 35, "queue": 85},
    {"name": "Southern Logistics", "city": "Houston", "state": "Texas", "region": "South",
     "capacity": 6000, "staff": 25, "queue": 60},
    {"name": "Mountain Fulfillment", "city": "Denver", "state": "Colorado", "region": "Central",
     "capacity": 5000, "staff": 20, "queue": 40},
]

CARRIERS = [
    {"name": "FastEx", "trucks": 120, "delay": 1.2},
    {"name": "ParcelPro", "trucks": 85, "delay": 2.5},
    {"name": "MailConnect", "trucks": 200, "delay": 3.8},
]


def ensure_mock_tables(conn, force=False):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS warehouses (
            warehouse_id INTEGER PRIMARY KEY AUTOINCREMENT,
            warehouse_name TEXT,
            city TEXT,
            state TEXT,
            region TEXT,
            capacity INTEGER,
            current_load INTEGER,
            staff_on_shift INTEGER,
            loading_queue INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS carriers (
            carrier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            carrier_name TEXT,
            active_trucks INTEGER,
            avg_delay_days REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            warehouse_id INTEGER,
            stock INTEGER DEFAULT 0,
            reserved INTEGER DEFAULT 0,
            incoming INTEGER DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(Product_ID),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
        )
    """)

    existing = cur.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0]
    if existing == 0 or force:
        cur.execute("DELETE FROM warehouses")
        cur.execute("DELETE FROM carriers")
        cur.execute("DELETE FROM inventory")

        for w in WAREHOUSES:
            load = int(w["capacity"] * random.uniform(0.4, 0.9))
            cur.execute(
                "INSERT INTO warehouses (warehouse_name, city, state, region, capacity, current_load, staff_on_shift, loading_queue) VALUES (?,?,?,?,?,?,?,?)",
                (w["name"], w["city"], w["state"], w["region"], w["capacity"], load, w["staff"], w["queue"])
            )

        for c in CARRIERS:
            cur.execute(
                "INSERT INTO carriers (carrier_name, active_trucks, avg_delay_days) VALUES (?,?,?)",
                (c["name"], c["trucks"], c["delay"])
            )

        products = pd.read_sql_query("SELECT Product_ID FROM products", conn)
        warehouse_ids = [1, 2, 3, 4, 5]
        inventory_rows = []
        for _, row in products.iterrows():
            for wh in random.sample(warehouse_ids, k=random.randint(1, 3)):
                stock = random.randint(5, 200)
                reserved = random.randint(0, int(stock * 0.6))
                incoming = random.randint(0, 50)
                inventory_rows.append((row["Product_ID"], wh, stock, reserved, incoming))

        cur.executemany(
            "INSERT INTO inventory (product_id, warehouse_id, stock, reserved, incoming) VALUES (?,?,?,?,?)",
            inventory_rows
        )

        conn.commit()
        print(f"Mock data created: {len(WAREHOUSES)} warehouses, {len(CARRIERS)} carriers, {len(inventory_rows)} inventory records")
    else:
        print(f"Mock tables already exist ({existing} warehouses)")


def main():
    conn = sqlite3.connect(DB)
    ensure_mock_tables(conn)
    conn.close()


if __name__ == "__main__":
    main()
