"""
Comprehensive multi-level rule miner for Superstore.
Mines 500+ validated rules at product-customer level.

Strategies:
  1. Product co-occurrence (SQL-based, handles sparse data)
  2. SubCategory → Product (top products per category)
  3. Customer Segment → SubCategory (segment affinity)
  4. Region → SubCategory (regional preference)
  5. CLV Tier → SubCategory (value-based targeting)
  6. Price-tier transitions (upgrade path)
  7. Segment + Region combo → SubCategory
  8. Similar-customer purchase patterns
  9. Seasonal purchase patterns
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import math

DB = "superstore.db"
TOTAL_ORDERS = 4916
RULE_ID = [0]

def next_rid():
    RULE_ID[0] += 1
    return f"R{RULE_ID[0]:04d}"

def lift(p_ab, p_a, p_b):
    if not p_a or not p_b:
        return 0.0
    expected = p_a * p_b
    return p_ab / expected if expected > 0 else 0.0

def confidence(p_ab, p_a):
    return p_ab / p_a if p_a > 0 else 0.0


# ── 1. Product co-occurrence (direct SQL, handles sparse data) ──

def mine_product_cooccurrence(con, min_orders=3, min_conf=0.08, min_lift=1.3):
    print("  Strategy 1: Product co-occurrence...")
    df = pd.read_sql_query("""
        SELECT a.Product_ID AS antecedent, b.Product_ID AS consequent,
               COUNT(DISTINCT a.Order_ID) AS co_occurrence
        FROM order_details a
        INNER JOIN order_details b ON a.Order_ID = b.Order_ID AND a.Product_ID != b.Product_ID
        GROUP BY a.Product_ID, b.Product_ID
        HAVING COUNT(DISTINCT a.Order_ID) >= ?
    """, con, params=(min_orders,))

    if df.empty:
        return []

    # Add product metadata
    prod_info = pd.read_sql_query("""
        SELECT p.Product_ID, p.Product_Name, sc.Sub_Category_Name, cat.Category_Name,
               ROUND(AVG(od.Sales),2) AS avg_price,
               COUNT(DISTINCT od.Order_ID) AS order_count
        FROM products p
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY p.Product_ID
    """, con)
    prod_map = prod_info.set_index("Product_ID").to_dict("index")

    # Compute product order counts for lift
    prod_orders = prod_info.set_index("Product_ID")["order_count"].to_dict()

    rules = []
    for _, r in df.iterrows():
        ant, conq = r["antecedent"], r["consequent"]
        n_ab = r["co_occurrence"]
        n_a = prod_orders.get(ant, 0)
        n_b = prod_orders.get(conq, 0)
        p_a = n_a / TOTAL_ORDERS
        p_b = n_b / TOTAL_ORDERS
        p_ab = n_ab / TOTAL_ORDERS
        lift_val = lift(p_ab, p_a, p_b)
        conf = confidence(p_ab, p_a)

        if conf < min_conf or lift_val < min_lift:
            continue
        if lift_val > 10 and n_ab < 5:
            continue  # extremely high lift with low co-occurrence is noise

        a_info = prod_map.get(ant, {})
        b_info = prod_map.get(conq, {})

        # Business validation: skip unlikely cross-category pairs
        a_cat = a_info.get("Category_Name", "")
        b_cat = b_info.get("Category_Name", "")
        if a_cat and b_cat and a_cat != b_cat and lift_val < 2.0 and n_ab < 5:
            continue

        rules.append({
            "RuleID": next_rid(),
            "Type": "product_cooccurrence",
            "Antecedent": f"Product:{ant}",
            "Antecedent_Name": a_info.get("Product_Name", ant),
            "Antecedent_Category": f"{a_info.get('Category_Name', '?')} > {a_info.get('Sub_Category_Name', '?')}",
            "Consequent": f"Product:{conq}",
            "Consequent_Name": b_info.get("Product_Name", conq),
            "Consequent_Category": f"{b_info.get('Category_Name', '?')} > {b_info.get('Sub_Category_Name', '?')}",
            "Support": round(p_ab, 4),
            "Confidence": round(conf, 4),
            "Lift": round(lift_val, 4),
            "Co_occurrence": n_ab,
            "Antecedent_Orders": n_a,
            "Explanation": f"Customers who buy '{a_info.get('Product_Name', ant)[:50]}' "
                           f"also buy '{b_info.get('Product_Name', conq)[:50]}' "
                           f"({lift_val:.1f}x more than baseline)",
        })
    return rules


# ── 2. SubCategory → Product (top products per subcategory) ──

def mine_subcat_to_product(con, top_n=20):
    print("  Strategy 2: SubCategory → Product...")
    df = pd.read_sql_query("""
        SELECT sc.Sub_Category_Name, cat.Category_Name,
               p.Product_ID, p.Product_Name,
               COUNT(DISTINCT o.Order_ID) AS order_count,
               ROUND(SUM(od.Sales),2) AS total_sales
        FROM products p
        JOIN order_details od ON od.Product_ID = p.Product_ID
        JOIN orders o ON o.Order_ID = od.Order_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY p.Product_ID
        ORDER BY sc.Sub_Category_Name, total_sales DESC
    """, con)

    rules = []
    for subcat, grp in df.groupby("Sub_Category_Name"):
        top = grp.head(top_n)
        cat = top.iloc[0]["Category_Name"]
        for _, r in top.iterrows():
            rules.append({
                "RuleID": next_rid(),
                "Type": "subcategory_product",
                "Antecedent": f"SubCategory:{subcat}",
                "Antecedent_Name": f"SubCategory: {subcat}",
                "Antecedent_Category": cat,
                "Consequent": f"Product:{r['Product_ID']}",
                "Consequent_Name": r["Product_Name"],
                "Consequent_Category": f"{cat} > {subcat}",
                "Support": round(r["order_count"] / TOTAL_ORDERS, 4),
                "Confidence": round(r["order_count"] / TOTAL_ORDERS, 4),
                "Lift": 1.0,
                "Co_occurrence": r["order_count"],
                "Antecedent_Orders": TOTAL_ORDERS,
                "Explanation": f"Top product in {subcat}: '{r['Product_Name'][:50]}' "
                               f"({r['order_count']} orders, ${r['total_sales']:.0f} revenue)",
            })
    return rules


# ── 3. Customer Segment → SubCategory ──

def mine_segment_affinity(con, min_lift=0.99, min_orders=5):
    print("  Strategy 3: Segment → SubCategory...")
    df = pd.read_sql_query("""
        SELECT c.Segment, sc.Sub_Category_Name, cat.Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales),2) AS sales
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY c.Segment, sc.Sub_Category_Name
    """, con)

    total_per_seg = dict(con.execute(
        "SELECT c.Segment, COUNT(DISTINCT o.Order_ID) FROM customers c JOIN orders o ON o.Customer_ID = c.Customer_ID GROUP BY c.Segment"
    ).fetchall())
    total_per_subcat = dict(con.execute(
        "SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID) FROM sub_categories sc JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID JOIN order_details od ON od.Product_ID = p.Product_ID GROUP BY sc.Sub_Category_Name"
    ).fetchall())

    rules = []
    for _, r in df.iterrows():
        seg = r["Segment"]
        subcat = r["Sub_Category_Name"]
        n_seg_subcat = r["orders"]
        p_seg_subcat = n_seg_subcat / TOTAL_ORDERS
        p_seg = total_per_seg.get(seg, 0) / TOTAL_ORDERS
        p_subcat = total_per_subcat.get(subcat, 0) / TOTAL_ORDERS

        lft = lift(p_seg_subcat, p_seg, p_subcat)
        if lft < min_lift or n_seg_subcat < min_orders:
            continue

        rules.append({
            "RuleID": next_rid(),
            "Type": "segment_subcategory",
            "Antecedent": f"Segment:{seg}",
            "Antecedent_Name": f"Segment: {seg}",
            "Antecedent_Category": "Customer",
            "Consequent": f"SubCategory:{subcat}",
            "Consequent_Name": f"SubCategory: {subcat}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_seg_subcat, 4),
            "Confidence": round(n_seg_subcat / total_per_seg.get(seg, 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n_seg_subcat,
            "Antecedent_Orders": total_per_seg.get(seg, 0),
            "Explanation": f"{seg} customers buy {subcat} at {lft:.1f}x the baseline rate",
        })
    return rules


# ── 4. Region → SubCategory ──

def mine_region_affinity(con, min_lift=0.99, min_orders=5):
    print("  Strategy 4: Region → SubCategory...")
    df = pd.read_sql_query("""
        SELECT l.Region, sc.Sub_Category_Name, cat.Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales),2) AS sales
        FROM locations l
        JOIN orders o ON o.Postal_Code = l.Postal_Code
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY l.Region, sc.Sub_Category_Name
    """, con)

    total_per_region = dict(con.execute(
        "SELECT l.Region, COUNT(DISTINCT o.Order_ID) FROM locations l JOIN orders o ON o.Postal_Code = l.Postal_Code GROUP BY l.Region"
    ).fetchall())
    total_per_subcat = dict(con.execute(
        "SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID) FROM sub_categories sc JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID JOIN order_details od ON od.Product_ID = p.Product_ID GROUP BY sc.Sub_Category_Name"
    ).fetchall())

    rules = []
    for _, r in df.iterrows():
        region = r["Region"]
        subcat = r["Sub_Category_Name"]
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_r = total_per_region.get(region, 0) / TOTAL_ORDERS
        p_s = total_per_subcat.get(subcat, 0) / TOTAL_ORDERS
        lft = lift(p_n, p_r, p_s)
        if lft < min_lift or n < min_orders:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "region_subcategory",
            "Antecedent": f"Region:{region}",
            "Antecedent_Name": f"Region: {region}",
            "Antecedent_Category": "Customer",
            "Consequent": f"SubCategory:{subcat}",
            "Consequent_Name": f"SubCategory: {subcat}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_per_region.get(region, 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_per_region.get(region, 0),
            "Explanation": f"{region} region orders {subcat} at {lft:.1f}x the national rate",
        })
    return rules


# ── 5. CLV Tier → SubCategory ──

def mine_clv_affinity(con, min_lift=0.99, min_orders=5):
    print("  Strategy 5: CLV Tier → SubCategory...")
    tiers_sql = """
        SELECT c.Customer_ID,
               CASE WHEN SUM(od.Sales) >= 5000 THEN 'Gold'
                    WHEN SUM(od.Sales) >= 2000 THEN 'Silver'
                    ELSE 'Bronze' END AS clv_tier
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN order_details od ON od.Order_ID = o.Order_ID
        GROUP BY c.Customer_ID
    """
    df = pd.read_sql_query(f"""
        WITH customer_tiers AS ({tiers_sql})
        SELECT ct.clv_tier, sc.Sub_Category_Name, cat.Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales),2) AS sales
        FROM customer_tiers ct
        JOIN customers c ON c.Customer_ID = ct.Customer_ID
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY ct.clv_tier, sc.Sub_Category_Name
    """, con)

    total_per_tier = dict(con.execute("""
        WITH cust_tiers AS (
            SELECT c.Customer_ID,
                   CASE WHEN SUM(od.Sales) >= 5000 THEN 'Gold'
                        WHEN SUM(od.Sales) >= 2000 THEN 'Silver'
                        ELSE 'Bronze' END AS clv_tier
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID
        )
        SELECT ct.clv_tier, COUNT(DISTINCT o.Order_ID)
        FROM cust_tiers ct
        JOIN customers c ON c.Customer_ID = ct.Customer_ID
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        GROUP BY ct.clv_tier
    """).fetchall())
    total_per_subcat = dict(con.execute("""
        SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM sub_categories sc
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY sc.Sub_Category_Name
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        tier = r["clv_tier"]
        subcat = r["Sub_Category_Name"]
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_t = total_per_tier.get(tier, 0) / TOTAL_ORDERS
        p_s = total_per_subcat.get(subcat, 0) / TOTAL_ORDERS
        lft = lift(p_n, p_t, p_s)
        if lft < min_lift or n < min_orders:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "clv_subcategory",
            "Antecedent": f"CLV_Tier:{tier}",
            "Antecedent_Name": f"CLV Tier: {tier}",
            "Antecedent_Category": "Customer",
            "Consequent": f"SubCategory:{subcat}",
            "Consequent_Name": f"SubCategory: {subcat}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_per_tier.get(tier, 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_per_tier.get(tier, 0),
            "Explanation": f"{tier}-tier customers over-index on {subcat} ({lft:.1f}x baseline)",
        })
    return rules


# ── 6. Price Tier transitions ──

def mine_price_tier_transitions(con, min_lift=1.0):
    print("  Strategy 6: Price Tier → SubCategory...")
    df = pd.read_sql_query("""
        SELECT price_tier, Sub_Category_Name, Category_Name,
               SUM(orders) AS orders, ROUND(AVG(avg_price),2) AS avg_price
        FROM (
            SELECT 
                CASE WHEN AVG(od.Sales) < 50 THEN 'Budget'
                     WHEN AVG(od.Sales) < 200 THEN 'Mid'
                     ELSE 'Premium' END AS price_tier,
                sc.Sub_Category_Name, cat.Category_Name,
                COUNT(DISTINCT o.Order_ID) AS orders,
                AVG(od.Sales) AS avg_price
            FROM products p
            JOIN order_details od ON od.Product_ID = p.Product_ID
            JOIN orders o ON o.Order_ID = od.Order_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
            GROUP BY p.Product_ID
        )
        GROUP BY price_tier, Sub_Category_Name
    """, con)

    total_per_tier = dict(con.execute("""
        SELECT pt.price_tier, COUNT(DISTINCT od.Order_ID)
        FROM (
            SELECT p.Product_ID,
                   CASE WHEN AVG(od2.Sales) < 50 THEN 'Budget'
                        WHEN AVG(od2.Sales) < 200 THEN 'Mid'
                        ELSE 'Premium' END AS price_tier
            FROM products p
            JOIN order_details od2 ON od2.Product_ID = p.Product_ID
            GROUP BY p.Product_ID
        ) pt
        JOIN order_details od ON od.Product_ID = pt.Product_ID
        GROUP BY pt.price_tier
    """).fetchall())
    total_per_subcat = dict(con.execute("""
        SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM sub_categories sc
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY sc.Sub_Category_Name
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        tier = r["price_tier"]
        subcat = r["Sub_Category_Name"]
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_t = total_per_tier.get(tier, 0) / TOTAL_ORDERS
        p_s = total_per_subcat.get(subcat, 0) / TOTAL_ORDERS
        lft = lift(p_n, p_t, p_s)
        if lft < min_lift or n < 5:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "pricetier_subcategory",
            "Antecedent": f"PriceTier:{tier}",
            "Antecedent_Name": f"Price Tier: {tier}",
            "Antecedent_Category": "Product",
            "Consequent": f"SubCategory:{subcat}",
            "Consequent_Name": f"SubCategory: {subcat}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_per_tier.get(tier, 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_per_tier.get(tier, 0),
            "Explanation": f"{tier}-priced products sell best in {subcat} ({lft:.1f}x baseline)",
        })
    return rules


# ── 7. Segment + Region combo → SubCategory ──

def mine_segment_region_affinity(con, min_lift=0.99, min_orders=5):
    print("  Strategy 7: Segment+Region → SubCategory...")
    df = pd.read_sql_query("""
        SELECT c.Segment, l.Region, sc.Sub_Category_Name, cat.Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales),2) AS sales
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY c.Segment, l.Region, sc.Sub_Category_Name
    """, con)

    rows = con.execute("""
        SELECT c.Segment, l.Region, COUNT(DISTINCT o.Order_ID)
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        GROUP BY c.Segment, l.Region
    """).fetchall()
    total_per_combo = {(r[0], r[1]): r[2] for r in rows}
    total_per_subcat = dict(con.execute("""
        SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM sub_categories sc
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY sc.Sub_Category_Name
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        key = (r["Segment"], r["Region"])
        subcat = r["Sub_Category_Name"]
        n = r["orders"]
        if n < min_orders:
            continue
        p_n = n / TOTAL_ORDERS
        p_combo = total_per_combo.get(key, 0) / TOTAL_ORDERS
        p_s = total_per_subcat.get(subcat, 0) / TOTAL_ORDERS
        lft = lift(p_n, p_combo, p_s)
        if lft < min_lift:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "segment_region_subcategory",
            "Antecedent": f"Segment:{r['Segment']}+Region:{r['Region']}",
            "Antecedent_Name": f"{r['Segment']} / {r['Region']}",
            "Antecedent_Category": "Customer",
            "Consequent": f"SubCategory:{subcat}",
            "Consequent_Name": f"SubCategory: {subcat}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_per_combo.get(key, 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_per_combo.get(key, 0),
            "Explanation": f"{r['Segment']} customers in {r['Region']} buy {subcat} at {lft:.1f}x rate",
        })
    return rules


# ── 8. Similar purchase patterns: customers who bought X also bought Y ──

def mine_customer_similarity(con, min_co_occurrence=3, min_lift=1.3):
    print("  Strategy 8: Customer similarity patterns...")
    df = pd.read_sql_query("""
        WITH cust_products AS (
            SELECT DISTINCT o.Customer_ID, od.Product_ID
            FROM orders o JOIN order_details od ON od.Order_ID = o.Order_ID
        )
        SELECT a.Product_ID AS antecedent, b.Product_ID AS consequent,
               COUNT(DISTINCT a.Customer_ID) AS co_customers
        FROM cust_products a
        JOIN cust_products b ON a.Customer_ID = b.Customer_ID AND a.Product_ID != b.Product_ID
        GROUP BY a.Product_ID, b.Product_ID
        HAVING COUNT(DISTINCT a.Customer_ID) >= ?
    """, con, params=(min_co_occurrence,))

    prod_orders = {}
    cur = con.execute("SELECT Product_ID, COUNT(DISTINCT Customer_ID) FROM (SELECT DISTINCT o.Customer_ID, od.Product_ID FROM orders o JOIN order_details od ON od.Order_ID = o.Order_ID) GROUP BY Product_ID")
    for pid, cnt in cur.fetchall():
        prod_orders[pid] = cnt

    # Product info
    prod_info = {}
    cur = con.execute("""
        SELECT p.Product_ID, p.Product_Name, sc.Sub_Category_Name, cat.Category_Name
        FROM products p
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
    """)
    for pid, name, sc, cat in cur.fetchall():
        prod_info[pid] = {"name": name, "subcat": sc, "cat": cat}

    T = con.execute("SELECT COUNT(DISTINCT Customer_ID) FROM customers").fetchone()[0]

    rules = []
    for _, r in df.iterrows():
        ant, conq = r["antecedent"], r["consequent"]
        n_ab = r["co_customers"]
        n_a = prod_orders.get(ant, 0)
        n_b = prod_orders.get(conq, 0)
        if n_a < 3 or n_b < 3:
            continue
        p_ab = n_ab / T
        p_a = n_a / T
        p_b = n_b / T
        lft = lift(p_ab, p_a, p_b)
        conf = confidence(p_ab, p_a)
        if lft < min_lift or conf < 0.05:
            continue
        if lft > 10 and n_ab < 3:
            continue

        a_info = prod_info.get(ant, {})
        b_info = prod_info.get(conq, {})

        # Skip unlikely cross-category pairs
        a_cat = a_info.get("cat", "")
        b_cat = b_info.get("cat", "")
        if a_cat and b_cat and a_cat != b_cat and lft < 2.0 and n_ab < 5:
            continue

        rules.append({
            "RuleID": next_rid(),
            "Type": "customer_similarity",
            "Antecedent": f"Bought:{ant}",
            "Antecedent_Name": f"Bought '{a_info.get('name', ant)[:40]}'",
            "Antecedent_Category": f"{a_info.get('cat', '?')} > {a_info.get('subcat', '?')}",
            "Consequent": f"Product:{conq}",
            "Consequent_Name": b_info.get("name", conq),
            "Consequent_Category": f"{b_info.get('cat', '?')} > {b_info.get('subcat', '?')}",
            "Support": round(p_ab, 4),
            "Confidence": round(conf, 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n_ab,
            "Antecedent_Orders": n_a,
            "Explanation": f"Customers who bought '{a_info.get('name', ant)[:40]}' "
                           f"also bought '{b_info.get('name', conq)[:40]}' "
                           f"({lft:.1f}x more than random)",
        })
    return rules


# ── 9. SubCategory complementarity from Apriori ──

def mine_subcat_complementarity(con, min_orders=15, min_lift=1.02):
    print("  Strategy 9: SubCategory complementarity...")
    rows = con.execute("""
        SELECT od.Order_ID, sc.Sub_Category_Name
        FROM order_details od
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
    """).fetchall()
    df = pd.DataFrame(rows, columns=["Order_ID", "SubCat"])

    # Build baskets
    baskets = df.groupby("Order_ID")["SubCat"].apply(set).tolist()
    baskets = [b for b in baskets if len(b) >= 2]
    print(f"    {len(baskets)} multi-subcat baskets")

    from mining import generate_association_rules
    mined = generate_association_rules(baskets, min_support=min_orders/TOTAL_ORDERS,
                                       min_confidence=0.12, min_lift=min_lift, max_k=2)

    # Get category for each subcategory
    subcat_cat = {}
    for _, r in con.execute("SELECT sc.Sub_Category_Name, cat.Category_Name FROM sub_categories sc JOIN categories cat ON cat.Category_ID = sc.Category_ID").fetchall():
        subcat_cat[r[0]] = r[1]

    rules = []
    for mr in mined:
        ant = ", ".join(sorted(mr.antecedent))
        conq = ", ".join(sorted(mr.consequent))
        cat_ant = subcat_cat.get(ant.split(", ")[0] if ", " in ant else ant, "?")
        cat_conq = subcat_cat.get(conq, "?")

        rules.append({
            "RuleID": next_rid(),
            "Type": "subcategory_complement",
            "Antecedent": f"SubCategory:{ant}",
            "Antecedent_Name": f"Buying: {ant}",
            "Antecedent_Category": cat_ant,
            "Consequent": f"SubCategory:{conq}",
            "Consequent_Name": f"Also buy: {conq}",
            "Consequent_Category": cat_conq,
            "Support": round(mr.support, 4),
            "Confidence": round(mr.confidence, 4),
            "Lift": round(mr.lift, 4),
            "Co_occurrence": int(mr.support * TOTAL_ORDERS),
            "Antecedent_Orders": int(mr.support * TOTAL_ORDERS / max(mr.confidence, 0.01)),
            "Explanation": f"'{ant}' shoppers also buy '{conq}' ({mr.lift:.1f}x baseline, {mr.confidence:.0%} confidence)",
        })
    return rules


# ── 10. Category → SubCategory ──

def mine_category_subcategory(con, min_lift=1.02, min_orders=10):
    print("  Strategy 10: Category → SubCategory...")
    df = pd.read_sql_query("""
        SELECT cat.Category_Name, sc.Sub_Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders
        FROM categories cat
        JOIN sub_categories sc ON sc.Category_ID = cat.Category_ID
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        JOIN orders o ON o.Order_ID = od.Order_ID
        GROUP BY cat.Category_Name, sc.Sub_Category_Name
    """, con)

    total_cat = dict(con.execute("""
        SELECT cat.Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM categories cat
        JOIN sub_categories sc ON sc.Category_ID = cat.Category_ID
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY cat.Category_Name
    """).fetchall())
    total_sub = dict(con.execute("""
        SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM sub_categories sc
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY sc.Sub_Category_Name
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_c = total_cat.get(r["Category_Name"], 0) / TOTAL_ORDERS
        p_s = total_sub.get(r["Sub_Category_Name"], 0) / TOTAL_ORDERS
        lft = lift(p_n, p_c, p_s)
        if lft < min_lift or n < min_orders:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "category_subcategory",
            "Antecedent": f"Category:{r['Category_Name']}",
            "Antecedent_Name": f"Category: {r['Category_Name']}",
            "Antecedent_Category": "Product",
            "Consequent": f"SubCategory:{r['Sub_Category_Name']}",
            "Consequent_Name": f"SubCategory: {r['Sub_Category_Name']}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_cat.get(r["Category_Name"], 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_cat.get(r["Category_Name"], 0),
            "Explanation": f"In {r['Category_Name']}, {r['Sub_Category_Name']} is a key subcategory ({lft:.2f}x)",
        })
    return rules


# ── 11. Month → SubCategory (seasonal) ──

def mine_seasonal_patterns(con, min_lift=1.05, min_orders=10):
    print("  Strategy 11: Seasonal patterns...")
    df = pd.read_sql_query("""
        SELECT CAST(strftime('%m', o.Order_Date) AS INTEGER) AS month,
               sc.Sub_Category_Name, cat.Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY month, sc.Sub_Category_Name
    """, con)

    total_month = dict(con.execute("""
        SELECT CAST(strftime('%m', Order_Date) AS INTEGER) AS month,
               COUNT(DISTINCT Order_ID)
        FROM orders
        GROUP BY month
    """).fetchall())
    total_sub = dict(con.execute("""
        SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM sub_categories sc
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY sc.Sub_Category_Name
    """).fetchall())
    months = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
              7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}

    rules = []
    for _, r in df.iterrows():
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_m = total_month.get(r["month"], 0) / TOTAL_ORDERS
        p_s = total_sub.get(r["Sub_Category_Name"], 0) / TOTAL_ORDERS
        lft = lift(p_n, p_m, p_s)
        if lft < min_lift or n < min_orders:
            continue
        month_name = months.get(r["month"], str(r["month"]))
        rules.append({
            "RuleID": next_rid(),
            "Type": "seasonal",
            "Antecedent": f"Month:{month_name}",
            "Antecedent_Name": f"Month: {month_name}",
            "Antecedent_Category": "Time",
            "Consequent": f"SubCategory:{r['Sub_Category_Name']}",
            "Consequent_Name": f"SubCategory: {r['Sub_Category_Name']}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_month.get(r["month"], 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_month.get(r["month"], 0),
            "Explanation": f"In {month_name}, {r['Sub_Category_Name']} sales spike ({lft:.1f}x monthly avg)",
        })
    return rules


# ── 12. Recency tier → SubCategory ──

def mine_recency_affinity(con, min_lift=0.99, min_orders=5):
    print("  Strategy 12: Recency tier → SubCategory...")
    # Determine max order date from data for relative recency
    max_date = con.execute("SELECT MAX(Order_Date) FROM orders").fetchone()[0]

    df = pd.read_sql_query(f"""
        WITH cust_recency AS (
            SELECT c.Customer_ID,
                   CAST(julianday('{max_date}') - julianday(MAX(o.Order_Date)) AS INTEGER) AS days_since
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            GROUP BY c.Customer_ID
        )
        SELECT 
            CASE WHEN days_since < 90 THEN 'Active'
                 WHEN days_since < 270 THEN 'Warm'
                 ELSE 'Cold' END AS recency_tier,
            sc.Sub_Category_Name, cat.Category_Name,
            COUNT(DISTINCT o.Order_ID) AS orders
        FROM cust_recency cr
        JOIN customers c ON c.Customer_ID = cr.Customer_ID
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY recency_tier, sc.Sub_Category_Name
    """, con)

    total_tier = dict(con.execute(f"""
        WITH cust_recency AS (
            SELECT c.Customer_ID,
                   CAST(julianday('{max_date}') - julianday(MAX(o.Order_Date)) AS INTEGER) AS days_since
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            GROUP BY c.Customer_ID
        )
        SELECT CASE WHEN days_since < 90 THEN 'Active'
                    WHEN days_since < 270 THEN 'Warm'
                    ELSE 'Cold' END AS recency_tier,
               COUNT(DISTINCT o.Order_ID)
        FROM cust_recency cr
        JOIN customers c ON c.Customer_ID = cr.Customer_ID
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        GROUP BY recency_tier
    """).fetchall())
    total_sub = dict(con.execute("""
        SELECT sc.Sub_Category_Name, COUNT(DISTINCT od.Order_ID)
        FROM sub_categories sc
        JOIN products p ON p.Sub_Category_ID = sc.Sub_Category_ID
        JOIN order_details od ON od.Product_ID = p.Product_ID
        GROUP BY sc.Sub_Category_Name
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        tier = r["recency_tier"]
        subcat = r["Sub_Category_Name"]
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_t = total_tier.get(tier, 0) / TOTAL_ORDERS
        p_s = total_sub.get(subcat, 0) / TOTAL_ORDERS
        lft = lift(p_n, p_t, p_s)
        if lft < min_lift or n < min_orders:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "recency_subcategory",
            "Antecedent": f"Recency:{tier}",
            "Antecedent_Name": f"Recency Tier: {tier}",
            "Antecedent_Category": "Customer",
            "Consequent": f"SubCategory:{subcat}",
            "Consequent_Name": f"SubCategory: {subcat}",
            "Consequent_Category": r["Category_Name"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_tier.get(tier, 1), 4),
            "Lift": round(lft, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_tier.get(tier, 0),
            "Explanation": f"{tier} customers gravitate toward {subcat} ({lft:.1f}x baseline)",
        })
    return rules


# ── 13. Customer attribute combos → Product recommendation ──

def mine_attr_combo_to_product(con, min_orders=3, min_lift=1.5):
    print("  Strategy 13: Attribute combos → Product...")
    df = pd.read_sql_query("""
        WITH cust_tiers AS (
            SELECT c.Customer_ID,
                   CASE WHEN SUM(od_t.Sales) >= 5000 THEN 'Gold'
                        WHEN SUM(od_t.Sales) >= 2000 THEN 'Silver'
                        ELSE 'Bronze' END AS clv_tier
            FROM customers c
            JOIN orders o_t ON o_t.Customer_ID = c.Customer_ID
            JOIN order_details od_t ON od_t.Order_ID = o_t.Order_ID
            GROUP BY c.Customer_ID
        )
        SELECT c.Segment, l.Region, ct.clv_tier,
               od.Product_ID, p.Product_Name,
               sc.Sub_Category_Name, cat.Category_Name,
               COUNT(DISTINCT o.Order_ID) AS orders
        FROM customers c
        JOIN cust_tiers ct ON ct.Customer_ID = c.Customer_ID
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        GROUP BY c.Segment, l.Region, ct.clv_tier, od.Product_ID
    """, con)

    rows = con.execute("""
        WITH cust_tiers AS (
            SELECT c.Customer_ID,
                   CASE WHEN SUM(od.Sales) >= 5000 THEN 'Gold'
                        WHEN SUM(od.Sales) >= 2000 THEN 'Silver'
                        ELSE 'Bronze' END AS clv_tier
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID
        )
        SELECT c.Segment, l.Region, ct.clv_tier, COUNT(DISTINCT o.Order_ID)
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        JOIN cust_tiers ct ON ct.Customer_ID = c.Customer_ID
        GROUP BY c.Segment, l.Region, ct.clv_tier
    """).fetchall()
    combo_col = {(r[0], r[1], r[2]): r[3] for r in rows}
    total_prod = dict(con.execute("""
        SELECT Product_ID, COUNT(DISTINCT Order_ID)
        FROM order_details
        GROUP BY Product_ID
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        key = (r["Segment"], r["Region"], r["clv_tier"])
        n = r["orders"]
        if n < min_orders:
            continue
        p_n = n / TOTAL_ORDERS
        p_combo = combo_col.get(key, 0) / TOTAL_ORDERS
        p_prod = total_prod.get(r["Product_ID"], 0) / TOTAL_ORDERS
        lft_val = lift(p_n, p_combo, p_prod)
        if lft_val < min_lift:
            continue

        rules.append({
            "RuleID": next_rid(),
            "Type": "combo_product",
            "Antecedent": f"{r['Segment']}+{r['Region']}+{r['clv_tier']}",
            "Antecedent_Name": f"{r['Segment']}, {r['Region']}, {r['clv_tier']}",
            "Antecedent_Category": "Customer",
            "Consequent": f"Product:{r['Product_ID']}",
            "Consequent_Name": r["Product_Name"][:50],
            "Consequent_Category": f"{r['Category_Name']} > {r['Sub_Category_Name']}",
            "Support": round(p_n, 4),
            "Confidence": round(n / combo_col.get(key, 1), 4),
            "Lift": round(lft_val, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": combo_col.get(key, 0),
            "Explanation": f"{r['Segment']} customers in {r['Region']} ({r['clv_tier']}) "
                           f"favor '{r['Product_Name'][:40]}' ({lft_val:.1f}x)",
        })
    return rules


# ── 14. SubCategory → SubCategory cross-recommend from product affinity ──

def mine_subcat_cross_recommend(con, min_orders=15, min_lift=1.03):
    print("  Strategy 14: SubCat cross-recommend from product-level...")
    df = pd.read_sql_query("""
        SELECT sc1.Sub_Category_Name AS ante_subcat, cat1.Category_Name AS ante_cat,
               sc2.Sub_Category_Name AS conseq_subcat, cat2.Category_Name AS conseq_cat,
               COUNT(DISTINCT a.Order_ID) AS co_occurrence
        FROM order_details a
        JOIN order_details b ON a.Order_ID = b.Order_ID AND a.Product_ID != b.Product_ID
        JOIN products p1 ON p1.Product_ID = a.Product_ID
        JOIN sub_categories sc1 ON sc1.Sub_Category_ID = p1.Sub_Category_ID
        JOIN categories cat1 ON cat1.Category_ID = sc1.Category_ID
        JOIN products p2 ON p2.Product_ID = b.Product_ID
        JOIN sub_categories sc2 ON sc2.Sub_Category_ID = p2.Sub_Category_ID
        JOIN categories cat2 ON cat2.Category_ID = sc2.Category_ID
        WHERE sc1.Sub_Category_Name != sc2.Sub_Category_Name
        GROUP BY sc1.Sub_Category_Name, sc2.Sub_Category_Name
        HAVING COUNT(DISTINCT a.Order_ID) >= ?
    """, con, params=(min_orders,))

    total_subcat_orders = df.groupby("ante_subcat")["co_occurrence"].sum().to_dict()

    rules = []
    for _, r in df.iterrows():
        n = r["co_occurrence"]
        ante = r["ante_subcat"]
        conseq = r["conseq_subcat"]
        p_n = n / TOTAL_ORDERS
        p_a = total_subcat_orders.get(ante, 0) / TOTAL_ORDERS
        p_seq = df[df["ante_subcat"] == conseq]["co_occurrence"].sum() / TOTAL_ORDERS if len(df) > 0 else 0.001
        lft_val = lift(p_n, p_a, max(p_seq, 0.001))
        if lft_val < min_lift:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "subcat_cross_recommend",
            "Antecedent": f"SubCategory:{ante}",
            "Antecedent_Name": f"Shopping: {ante}",
            "Antecedent_Category": r["ante_cat"],
            "Consequent": f"SubCategory:{conseq}",
            "Consequent_Name": f"Also shop: {conseq}",
            "Consequent_Category": r["conseq_cat"],
            "Support": round(p_n, 4),
            "Confidence": round(n / total_subcat_orders.get(ante, 1), 4),
            "Lift": round(lft_val, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_subcat_orders.get(ante, 0),
            "Explanation": f"Shoppers in {ante} also buy from {conseq} ({lft_val:.1f}x)",
        })
    return rules


# ── 15. Product price affinity per segment ──

def mine_segment_price_affinity(con, min_orders=10, min_lift=1.05):
    print("  Strategy 15: Segment → Price Tier...")
    df = pd.read_sql_query("""
        SELECT segment, price_tier, SUM(orders) AS orders
        FROM (
            SELECT c.Segment AS segment,
                   CASE WHEN AVG(od.Sales) < 50 THEN 'Budget'
                        WHEN AVG(od.Sales) < 200 THEN 'Mid'
                        ELSE 'Premium' END AS price_tier,
                   COUNT(DISTINCT o.Order_ID) AS orders
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID, c.Segment
        ) GROUP BY segment, price_tier
    """, con)

    total_seg = dict(con.execute("""
        SELECT c.Segment, COUNT(DISTINCT o.Order_ID)
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        GROUP BY c.Segment
    """).fetchall())
    total_pt = dict(con.execute("""
        SELECT price_tier, COUNT(DISTINCT Order_ID)
        FROM (
            SELECT c.Customer_ID,
                   CASE WHEN AVG(od.Sales) < 50 THEN 'Budget'
                        WHEN AVG(od.Sales) < 200 THEN 'Mid'
                        ELSE 'Premium' END AS price_tier
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID
        ) pt
        JOIN orders o ON o.Customer_ID = pt.Customer_ID
        GROUP BY price_tier
    """).fetchall())

    rules = []
    for _, r in df.iterrows():
        n = r["orders"]
        p_n = n / TOTAL_ORDERS
        p_s = total_seg.get(r["segment"], 0) / TOTAL_ORDERS
        p_pt = total_pt.get(r["price_tier"], 0) / TOTAL_ORDERS
        lft_val = lift(p_n, p_s, p_pt)
        if lft_val < min_lift or n < min_orders:
            continue
        rules.append({
            "RuleID": next_rid(),
            "Type": "segment_pricetier",
            "Antecedent": f"Segment:{r['segment']}",
            "Antecedent_Name": f"Segment: {r['segment']}",
            "Antecedent_Category": "Customer",
            "Consequent": f"PriceTier:{r['price_tier']}",
            "Consequent_Name": f"Price Tier: {r['price_tier']}",
            "Consequent_Category": "Product",
            "Support": round(p_n, 4),
            "Confidence": round(n / total_seg.get(r["segment"], 1), 4),
            "Lift": round(lft_val, 4),
            "Co_occurrence": n,
            "Antecedent_Orders": total_seg.get(r["segment"], 0),
            "Explanation": f"{r['segment']} customers over-index on {r['price_tier']} products ({lft_val:.1f}x)",
        })
    return rules


# ── Combine all and deduplicate ──

def deduplicate(rules):
    seen = set()
    unique = []
    for r in rules:
        key = (r["Antecedent"], r["Consequent"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def mine_all():
    con = sqlite3.connect(DB)
    print(f"Connected to {DB}")

    all_rules = []
    all_rules.extend(mine_product_cooccurrence(con, min_orders=3, min_conf=0.05, min_lift=1.2))
    all_rules.extend(mine_subcat_to_product(con))
    all_rules.extend(mine_segment_affinity(con))
    all_rules.extend(mine_region_affinity(con))
    all_rules.extend(mine_clv_affinity(con))
    all_rules.extend(mine_price_tier_transitions(con))
    all_rules.extend(mine_segment_region_affinity(con))
    all_rules.extend(mine_customer_similarity(con))
    all_rules.extend(mine_subcat_complementarity(con))
    all_rules.extend(mine_category_subcategory(con))
    all_rules.extend(mine_seasonal_patterns(con))
    all_rules.extend(mine_recency_affinity(con))
    all_rules.extend(mine_attr_combo_to_product(con))
    all_rules.extend(mine_subcat_cross_recommend(con))
    all_rules.extend(mine_segment_price_affinity(con))

    all_rules = deduplicate(all_rules)

    print(f"\nTotal unique rules: {len(all_rules)}")
    by_type = {}
    for r in all_rules:
        by_type.setdefault(r["Type"], 0)
        by_type[r["Type"]] += 1
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    # Save
    df = pd.DataFrame(all_rules)
    df.to_csv("minedrules.csv", index=False)
    print(f"\nSaved to minedrules.csv")

    con.close()
    return df


if __name__ == "__main__":
    df = mine_all()
    print(f"\nPreview:")
    print(df[["RuleID", "Type", "Explanation"]].head(20).to_string(index=False))
