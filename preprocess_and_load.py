import sqlite3
import pandas as pd
import numpy as np

DB_PATH = "superstore.db"
CSV_PATH = "Data.csv"

# ── 1. Read raw data (matching notebook) ──
data = pd.read_csv(CSV_PATH)
print(f"Loaded {len(data):,} rows")

# ── 2. Drop null postal codes (notebook does this) ──
full_data = data.dropna(subset=["Postal Code"]).copy()
print(f"After dropping null postal codes: {len(full_data):,} rows")

# ── 3. Parse dates (notebook does this) ──
full_data = full_data.copy()
full_data["Order Date"] = pd.to_datetime(
    full_data["Order Date"], format="%d/%m/%Y", errors="coerce"
)
full_data["Ship Date"] = pd.to_datetime(
    full_data["Ship Date"], format="%d/%m/%Y", errors="coerce"
)

# ── 4. Create normalized tables (exact notebook logic) ──

# Ship Modes
ship_modes = (
    full_data[["Ship Mode"]]
    .drop_duplicates()
    .reset_index(drop=True)
)
ship_modes["Ship_Mode_ID"] = ship_modes.index + 1
ship_modes = ship_modes[["Ship_Mode_ID", "Ship Mode"]].rename(
    columns={"Ship Mode": "Ship_Mode_Name"}
)

# Customers
customers = (
    full_data[["Customer ID", "Customer Name", "Segment"]]
    .drop_duplicates()
)
customers.columns = ["Customer_ID", "Customer_Name", "Segment"]

# Locations
locations = (
    full_data[["Postal Code", "City", "State", "Country", "Region"]]
    .drop_duplicates()
)
locations.columns = ["Postal_Code", "City", "State", "Country", "Region"]

# Categories
categories = (
    full_data[["Category"]]
    .drop_duplicates()
    .reset_index(drop=True)
)
categories["Category_ID"] = categories.index + 1
categories = categories[["Category_ID", "Category"]].rename(
    columns={"Category": "Category_Name"}
)

# Sub Categories (linked to Category)
sub_categories = (
    full_data[["Category", "Sub-Category"]]
    .drop_duplicates()
)
sub_categories = sub_categories.merge(
    categories, left_on="Category", right_on="Category_Name"
)
sub_categories = sub_categories.drop(columns="Category")
sub_categories["Sub_Category_ID"] = range(1, len(sub_categories) + 1)
sub_categories = sub_categories[["Sub_Category_ID", "Category_ID", "Sub-Category"]]
sub_categories = sub_categories.rename(columns={"Sub-Category": "Sub_Category_Name"})

# Products (notebook keeps duplicate Product_IDs with different names — no PK enforced)
products = (
    full_data[["Product ID", "Product Name", "Sub-Category"]]
    .drop_duplicates()
)
products = products.merge(
    sub_categories[["Sub_Category_ID", "Sub_Category_Name"]],
    left_on="Sub-Category",
    right_on="Sub_Category_Name",
)
products = products[["Product ID", "Sub_Category_ID", "Product Name"]]
products.columns = ["Product_ID", "Sub_Category_ID", "Product_Name"]

# Orders
orders = (
    full_data[["Order ID", "Order Date", "Ship Date", "Ship Mode", "Customer ID", "Postal Code"]]
    .drop_duplicates()
)
orders = orders.merge(
    ship_modes, left_on="Ship Mode", right_on="Ship_Mode_Name"
)
orders = orders[["Order ID", "Order Date", "Ship Date", "Ship_Mode_ID", "Customer ID", "Postal Code"]]
orders.columns = ["Order_ID", "Order_Date", "Ship_Date", "Ship_Mode_ID", "Customer_ID", "Postal_Code"]

# Order Details (the fact table)
order_details = full_data[["Order ID", "Product ID", "Sales"]].copy()
order_details["Order_Detail_ID"] = range(1, len(order_details) + 1)
order_details = order_details[["Order_Detail_ID", "Order ID", "Product ID", "Sales"]]
order_details.columns = ["Order_Detail_ID", "Order_ID", "Product_ID", "Sales"]

print(f"\nTables created (matching notebook):")
print(f"  Customers:       {len(customers):,}")
print(f"  Locations:       {len(locations):,}")
print(f"  Ship_Modes:      {len(ship_modes)}")
print(f"  Categories:      {len(categories)}")
print(f"  Sub_Categories:  {len(sub_categories)}")
print(f"  Products:        {len(products):,}")
print(f"  Orders:          {len(orders):,}")
print(f"  Order_Details:   {len(order_details):,}")

# ── 5. Write to SQLite ──
con = sqlite3.connect(DB_PATH)
cur = con.cursor()

cur.execute("PRAGMA foreign_keys = ON")

cur.execute("""
CREATE TABLE IF NOT EXISTS customers (
    Customer_ID   TEXT PRIMARY KEY,
    Customer_Name TEXT NOT NULL,
    Segment       TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS locations (
    Postal_Code REAL NOT NULL,
    City        TEXT NOT NULL,
    State       TEXT NOT NULL,
    Country     TEXT NOT NULL,
    Region      TEXT NOT NULL,
    PRIMARY KEY (Postal_Code, City, State)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS ship_modes (
    Ship_Mode_ID   INTEGER PRIMARY KEY,
    Ship_Mode_Name TEXT NOT NULL UNIQUE
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS categories (
    Category_ID   INTEGER PRIMARY KEY,
    Category_Name TEXT NOT NULL UNIQUE
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS sub_categories (
    Sub_Category_ID   INTEGER PRIMARY KEY,
    Category_ID       INTEGER NOT NULL REFERENCES categories(Category_ID),
    Sub_Category_Name TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS products (
    Product_ID      TEXT NOT NULL,
    Sub_Category_ID INTEGER NOT NULL REFERENCES sub_categories(Sub_Category_ID),
    Product_Name    TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    Order_ID     TEXT PRIMARY KEY,
    Order_Date   TEXT NOT NULL,
    Ship_Date    TEXT NOT NULL,
    Ship_Mode_ID INTEGER NOT NULL REFERENCES ship_modes(Ship_Mode_ID),
    Customer_ID  TEXT NOT NULL REFERENCES customers(Customer_ID),
    Postal_Code  REAL NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS order_details (
    Order_Detail_ID INTEGER PRIMARY KEY,
    Order_ID        TEXT NOT NULL REFERENCES orders(Order_ID),
    Product_ID      TEXT NOT NULL,
    Sales           REAL NOT NULL
)
""")

# Clear existing data
for table in ["order_details", "orders", "products", "sub_categories",
              "categories", "ship_modes", "locations", "customers"]:
    cur.execute(f"DELETE FROM {table}")

# Insert
customers.to_sql("customers", con, if_exists="append", index=False)
locations.to_sql("locations", con, if_exists="append", index=False)
ship_modes.to_sql("ship_modes", con, if_exists="append", index=False)
categories.to_sql("categories", con, if_exists="append", index=False)
sub_categories.to_sql("sub_categories", con, if_exists="append", index=False)
products.to_sql("products", con, if_exists="append", index=False)
orders.to_sql("orders", con, if_exists="append", index=False)
order_details.to_sql("order_details", con, if_exists="append", index=False)

# Indexes for BI performance
cur.executescript("""
CREATE INDEX IF NOT EXISTS idx_products_id ON products(Product_ID);
CREATE INDEX IF NOT EXISTS idx_products_subcat ON products(Sub_Category_ID);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(Customer_ID);
CREATE INDEX IF NOT EXISTS idx_orders_ship_mode ON orders(Ship_Mode_ID);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(Order_Date);
CREATE INDEX IF NOT EXISTS idx_order_details_order ON order_details(Order_ID);
CREATE INDEX IF NOT EXISTS idx_order_details_product ON order_details(Product_ID);
CREATE INDEX IF NOT EXISTS idx_subcat_category ON sub_categories(Category_ID);
""")

con.commit()
con.close()
print(f"\n✓ Database written to {DB_PATH}")
