"""
Knowledge Base v2 for the Superstore Recommendation System.

Fixes vs v1:
  - Customer->SubCategory purchase stats are now AGGREGATED per (customer, subcat)
    pair, computed in SQL, instead of being clobbered in a Python loop
    (v1 bug: `facts["has_bought_subcategory"] = sc` inside a `for sc in bought_subcats`
    loop meant only the last subcategory iterated ever survived).
  - `days_since_<subcat>_purchase` is now a REAL date computed from the data,
    not a hardcoded `30 if bought else 999`.
  - Exposes basket-level data (order_id -> set of sub-categories) so the
    mining module can run Apriori over real transactions.
  - Graph edges carry real weights (count, total $, last_date) instead of
    being a single decorative string label.
"""

import sqlite3
import networkx as nx
import pandas as pd
from datetime import datetime

DB = "superstore.db"

# ── Symbol definitions (the vocabulary of our KB) ──
CLV_TIERS = {"Bronze": (0, 2000), "Silver": (2000, 5000), "Gold": (5000, 1e12)}
RECENCY_TIERS = {"Active": (0, 90), "Warm": (90, 180), "Cold": (180, 1e12)}
FREQUENCY_TIERS = {"Low": (0, 3), "Medium": (3, 6), "High": (6, 1e12)}
PRICE_TIERS = {"Budget": (0, 50), "Mid": (50, 200), "Premium": (200, 1e12)}
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
REGIONS = ["East", "West", "Central", "South"]
SHIP_MODES = ["Same Day", "First Class", "Second Class", "Standard Class"]
CATEGORIES = ["Furniture", "Office Supplies", "Technology"]

SYMBOL_DICT = {
    "Segment": SEGMENTS,
    "Region": REGIONS,
    "Ship Mode": SHIP_MODES,
    "Category": CATEGORIES,
    "CLV Tier": list(CLV_TIERS.keys()),
    "Recency Tier": list(RECENCY_TIERS.keys()),
    "Frequency Tier": list(FREQUENCY_TIERS.keys()),
    "Price Tier": list(PRICE_TIERS.keys()),
}


def _tier(value, tiers):
    for name, (lo, hi) in tiers.items():
        if lo <= value < hi:
            return name
    return list(tiers.keys())[-1]


class KnowledgeBase:
    def __init__(self, db_path=DB):
        self.con = sqlite3.connect(db_path)
        self.G = nx.DiGraph()

        # Fast-lookup side tables (avoid re-walking the graph for fact-building)
        self.customer_subcat_stats = {}   # {cust_id: {subcat: {"count","total","last_date"}}}
        self.customer_product_stats = {}  # {cust_id: {prod_id: {"count","total"}}}
        self.baskets = []                 # list[set[str]] of sub-categories, one per order

        self._build()

    # ── Helpers ──
    def _q(self, sql, params=None):
        return pd.read_sql_query(sql, self.con, params=params)

    def _add(self, eid, etype, **attrs):
        attrs["type"] = etype
        if eid not in self.G:
            self.G.add_node(eid, **attrs)
        else:
            self.G.nodes[eid].update(attrs)
        return eid

    def _rel(self, src, dst, label, **attrs):
        attrs["label"] = label
        self.G.add_edge(src, dst, **attrs)

    # ── Build everything ──
    def _build(self):
        self._add_categories()
        self._add_subcategories()
        self._add_segments()
        self._add_regions()
        self._add_ship_modes()
        self._add_price_tiers()
        self._add_products()
        self._add_locations()
        self._add_customers()
        self._add_customer_subcategory_stats()
        self._add_customer_product_stats()
        self._add_baskets()
        self._add_ship_mode_usage()

    def _add_categories(self):
        for _, r in self._q("SELECT * FROM categories").iterrows():
            self._add(f"cat:{r['Category_Name']}", "Category", name=r["Category_Name"])

    def _add_subcategories(self):
        for _, r in self._q("""
            SELECT sc.*, cat.Category_Name FROM sub_categories sc
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
        """).iterrows():
            eid = self._add(f"subcat:{r['Sub_Category_Name']}", "SubCategory",
                             name=r["Sub_Category_Name"], category=r["Category_Name"])
            self._rel(eid, f"cat:{r['Category_Name']}", "belongs_to")

    def _add_segments(self):
        for s in SEGMENTS:
            self._add(f"seg:{s}", "Segment", name=s)

    def _add_regions(self):
        for r in REGIONS:
            self._add(f"region:{r}", "Region", name=r)

    def _add_ship_modes(self):
        for _, r in self._q("SELECT * FROM ship_modes").iterrows():
            self._add(f"ship:{r['Ship_Mode_Name']}", "ShipMode", name=r["Ship_Mode_Name"])

    def _add_price_tiers(self):
        for t in PRICE_TIERS:
            self._add(f"tier:{t}", "PriceTier", name=t)

    def _add_products(self):
        top = self._q("""
            SELECT p.Product_ID, p.Product_Name, sc.Sub_Category_Name,
                   cat.Category_Name, ROUND(AVG(od.Sales), 2) AS avg_price,
                   SUM(od.Sales) AS total_sales
            FROM products p
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
            JOIN order_details od ON od.Product_ID = p.Product_ID
            GROUP BY p.Product_ID
            ORDER BY total_sales DESC
            LIMIT 200
        """)
        for _, r in top.iterrows():
            tier = _tier(r["avg_price"], PRICE_TIERS)
            eid = self._add(f"prod:{r['Product_ID']}", "Product",
                             name=r["Product_Name"], sub_category=r["Sub_Category_Name"],
                             category=r["Category_Name"], price_tier=tier,
                             avg_price=r["avg_price"], total_sales=r["total_sales"])
            self._rel(eid, f"subcat:{r['Sub_Category_Name']}", "belongs_to")
            self._rel(eid, f"tier:{tier}", "price_tier")

    def _add_locations(self):
        locs = self._q("SELECT DISTINCT City, State, Region FROM locations ORDER BY Region, State")
        for _, r in locs.iterrows():
            eid = self._add(f"loc:{r['City']}|{r['State']}", "Location",
                             city=r["City"], state=r["State"], region=r["Region"])
            self._rel(eid, f"region:{r['Region']}", "in_region")

    def _add_customers(self):
        today = datetime.now()
        stats = self._q("""
            SELECT c.Customer_ID, c.Customer_Name, c.Segment,
                   COUNT(DISTINCT o.Order_ID) AS order_count,
                   ROUND(SUM(od.Sales), 2) AS total_spent,
                   ROUND(AVG(od.Sales), 2) AS avg_order,
                   MAX(o.Order_Date) AS last_order
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID
        """)
        # Category affinity for all customers in one query (was N+1 in v1)
        aff_all = self._q("""
            SELECT o.Customer_ID, cat.Category_Name, SUM(od.Sales) AS s
            FROM orders o
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN products p ON p.Product_ID = od.Product_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
            GROUP BY o.Customer_ID, cat.Category_Name
        """)
        affinity_map = (aff_all.sort_values("s", ascending=False)
                                .groupby("Customer_ID").first()["Category_Name"].to_dict())

        for _, r in stats.iterrows():
            clv = _tier(r["total_spent"], CLV_TIERS)
            last = pd.Timestamp(r["last_order"])
            days_since = (today - last).days if pd.notna(last) else 999
            recency = _tier(days_since, RECENCY_TIERS)
            freq = _tier(r["order_count"], FREQUENCY_TIERS)
            affinity = affinity_map.get(r["Customer_ID"], "Unknown")

            eid = self._add(f"cust:{r['Customer_ID']}", "Customer",
                             name=r["Customer_Name"], segment=r["Segment"],
                             clv_tier=clv, recency_tier=recency, frequency_tier=freq,
                             category_affinity=affinity, total_spent=r["total_spent"],
                             order_count=r["order_count"], days_since_last=days_since)
            self._rel(eid, f"seg:{r['Segment']}", "belongs_to")

    def _add_customer_subcategory_stats(self):
        """The key bug-fix: one aggregated row per (customer, subcategory),
        not a Python loop that overwrites a single dict key."""
        today = datetime.now()
        rows = self._q("""
            SELECT o.Customer_ID, sc.Sub_Category_Name,
                   COUNT(*) AS cnt, ROUND(SUM(od.Sales), 2) AS total,
                   MAX(o.Order_Date) AS last_date
            FROM orders o
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN products p ON p.Product_ID = od.Product_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
            GROUP BY o.Customer_ID, sc.Sub_Category_Name
        """)
        for _, r in rows.iterrows():
            cust_id, subcat = r["Customer_ID"], r["Sub_Category_Name"]
            last = pd.Timestamp(r["last_date"])
            days_since = (today - last).days if pd.notna(last) else 999
            self.customer_subcat_stats.setdefault(cust_id, {})[subcat] = {
                "count": int(r["cnt"]), "total": float(r["total"]), "days_since": days_since,
            }
            cust_node, subcat_node = f"cust:{cust_id}", f"subcat:{subcat}"
            if cust_node in self.G and subcat_node in self.G:
                self._rel(cust_node, subcat_node, "bought_subcategory",
                           count=int(r["cnt"]), total=float(r["total"]), days_since=days_since)

    def _add_customer_product_stats(self):
        buys = self._q("""
            SELECT o.Customer_ID, od.Product_ID, COUNT(*) AS times,
                   ROUND(SUM(od.Sales),2) AS total
            FROM orders o
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY o.Customer_ID, od.Product_ID
            HAVING SUM(od.Sales) > 500
            ORDER BY total DESC
            LIMIT 500
        """)
        for _, r in buys.iterrows():
            cust, prod = f"cust:{r['Customer_ID']}", f"prod:{r['Product_ID']}"
            self.customer_product_stats.setdefault(r["Customer_ID"], {})[r["Product_ID"]] = {
                "count": int(r["times"]), "total": float(r["total"]),
            }
            if cust in self.G and prod in self.G:
                self._rel(cust, prod, "bought", count=int(r["times"]), total=float(r["total"]))

    def _add_baskets(self):
        """One basket per order = set of sub-categories purchased together.
        This is the transaction data Apriori mines over."""
        rows = self._q("""
            SELECT od.Order_ID, sc.Sub_Category_Name
            FROM order_details od
            JOIN products p ON p.Product_ID = od.Product_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        """)
        grouped = rows.groupby("Order_ID")["Sub_Category_Name"].apply(set)
        self.baskets = list(grouped.values)

    def _add_ship_mode_usage(self):
        ship_use = self._q("""
            SELECT sm.Ship_Mode_Name, COUNT(*) AS cnt
            FROM orders o JOIN ship_modes sm ON sm.Ship_Mode_ID = o.Ship_Mode_ID
            GROUP BY sm.Ship_Mode_Name
        """)
        for _, r in ship_use.iterrows():
            eid = f"ship:{r['Ship_Mode_Name']}"
            if eid in self.G:
                self.G.nodes[eid]["cnt"] = r["cnt"]

    # ── Query helpers ──
    def get_entity(self, eid):
        return dict(self.G.nodes[eid]) if eid in self.G else None

    def search_entities(self, query_str, etype=None, limit=50):
        results, q = [], query_str.lower()
        for nid, attrs in self.G.nodes(data=True):
            if etype and attrs.get("type") != etype:
                continue
            if q in nid.lower() or q in attrs.get("name", "").lower():
                results.append((nid, dict(attrs)))
        return results[:limit]

    def get_neighbors(self, eid, max_nodes=100):
        if eid not in self.G:
            return []
        out = []
        for src, dst, data in self.G.edges(eid, data=True):
            other = dst if src == eid else src
            out.append((other, dict(self.G.nodes[other]), dict(data)))
        return out[:max_nodes]

    def get_symbols(self):
        return dict(SYMBOL_DICT)

    def get_entity_types(self):
        return sorted({attrs.get("type") for _, attrs in self.G.nodes(data=True) if attrs.get("type")})

    def get_type_count(self):
        counts = {}
        for _, attrs in self.G.nodes(data=True):
            t = attrs.get("type", "Unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def get_all_of_type(self, etype, limit=500):
        out = []
        for nid, attrs in self.G.nodes(data=True):
            if attrs.get("type") == etype:
                out.append((nid, dict(attrs)))
                if len(out) >= limit:
                    break
        return out

    def get_baskets(self):
        """list[set[str]] — one set of sub-category names per order, for Apriori."""
        return self.baskets


if __name__ == "__main__":
    kb = KnowledgeBase()
    print(f"Graph: {kb.G.number_of_nodes()} nodes, {kb.G.number_of_edges()} edges")
    for t, c in sorted(kb.get_type_count().items()):
        print(f"  {t}: {c}")
    print(f"Baskets: {len(kb.baskets)}")
