import sqlite3
import networkx as nx
import pandas as pd
from datetime import datetime, timedelta

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
    def __init__(self):
        self.con = sqlite3.connect(DB)
        self.G = nx.DiGraph()
        self._build()

    # ── Helpers ──
    def _q(self, sql):
        return pd.read_sql_query(sql, self.con)

    def _add(self, eid, etype, **attrs):
        attrs["type"] = etype
        if eid not in self.G:
            self.G.add_node(eid, **attrs)
        else:
            self.G.nodes[eid].update(attrs)
        return eid

    def _rel(self, src, dst, label):
        self.G.add_edge(src, dst, label=label)

    # ── Build everything ──
    def _build(self):
        self._add_categories()
        self._add_subcategories()
        self._add_products()
        self._add_customers()
        self._add_segments()
        self._add_locations()
        self._add_regions()
        self._add_ship_modes()
        self._add_price_tiers()
        self._add_orders_and_details()

    def _add_categories(self):
        for _, r in self._q("SELECT * FROM categories").iterrows():
            self._add(f"cat:{r['Category_Name']}", "Category",
                      name=r["Category_Name"])

    def _add_subcategories(self):
        for _, r in self._q("""
            SELECT sc.*, cat.Category_Name FROM sub_categories sc
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
        """).iterrows():
            eid = self._add(f"subcat:{r['Sub_Category_Name']}", "SubCategory",
                            name=r["Sub_Category_Name"],
                            category=r["Category_Name"])
            self._rel(eid, f"cat:{r['Category_Name']}", "belongs_to")

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
                            name=r["Product_Name"],
                            sub_category=r["Sub_Category_Name"],
                            category=r["Category_Name"],
                            price_tier=tier,
                            avg_price=r["avg_price"],
                            total_sales=r["total_sales"])
            self._rel(eid, f"subcat:{r['Sub_Category_Name']}", "belongs_to")
            self._rel(eid, f"tier:{tier}", "price_tier")

    def _add_customers(self):
        today = datetime.now()
        stats = self._q("""
            SELECT c.Customer_ID, c.Customer_Name, c.Segment,
                   COUNT(DISTINCT o.Order_ID) AS order_count,
                   ROUND(SUM(od.Sales), 2) AS total_spent,
                   ROUND(AVG(od.Sales), 2) AS avg_order,
                   MAX(o.Order_Date) AS last_order,
                   (SELECT ROUND(SUM(od2.Sales),2) FROM orders o2
                    JOIN order_details od2 ON od2.Order_ID = o2.Order_ID
                    WHERE o2.Customer_ID = c.Customer_ID
                      AND o2.Order_Date >= DATE('now', '-1 year')) AS year_spend
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID
        """)
        for _, r in stats.iterrows():
            clv = _tier(r["total_spent"], CLV_TIERS)
            last = pd.Timestamp(r["last_order"])
            days_since = (today - last).days if pd.notna(last) else 999
            recency = _tier(days_since, RECENCY_TIERS)
            freq = _tier(r["order_count"], FREQUENCY_TIERS)

            # Category affinity (which category they spend most on)
            aff = self._q(f"""
                SELECT cat.Category_Name, ROUND(SUM(od.Sales),2) AS s
                FROM orders o
                JOIN order_details od ON od.Order_ID = o.Order_ID
                JOIN products p ON p.Product_ID = od.Product_ID
                JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
                JOIN categories cat ON cat.Category_ID = sc.Category_ID
                WHERE o.Customer_ID = '{r['Customer_ID']}'
                GROUP BY cat.Category_Name ORDER BY s DESC LIMIT 1
            """)
            affinity = aff.iloc[0]["Category_Name"] if len(aff) > 0 else "Unknown"

            eid = self._add(f"cust:{r['Customer_ID']}", "Customer",
                            name=r["Customer_Name"],
                            segment=r["Segment"],
                            clv_tier=clv,
                            recency_tier=recency,
                            frequency_tier=freq,
                            category_affinity=affinity,
                            total_spent=r["total_spent"],
                            order_count=r["order_count"],
                            days_since_last=days_since)
            self._rel(eid, f"seg:{r['Segment']}", "belongs_to")

    def _add_locations(self):
        locs = self._q("""
            SELECT DISTINCT l.City, l.State, l.Region
            FROM locations l
            ORDER BY l.Region, l.State
        """)
        for _, r in locs.iterrows():
            eid = self._add(f"loc:{r['City']}|{r['State']}", "Location",
                            city=r["City"], state=r["State"], region=r["Region"])
            self._rel(eid, f"region:{r['Region']}", "in_region")

    def _add_ship_modes(self):
        for _, r in self._q("SELECT * FROM ship_modes").iterrows():
            self._add(f"ship:{r['Ship_Mode_Name']}", "ShipMode",
                      name=r["Ship_Mode_Name"])

    def _add_segments(self):
        for s in SEGMENTS:
            self._add(f"seg:{s}", "Segment", name=s)

    def _add_regions(self):
        for r in REGIONS:
            self._add(f"region:{r}", "Region", name=r)

    def _add_price_tiers(self):
        for t in PRICE_TIERS:
            self._add(f"tier:{t}", "PriceTier", name=t)

    def _add_orders_and_details(self):
        # Add some aggregate relations: Customer -> bought -> Product (simplified)
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
            # Only add edge if both nodes exist
            cust = f"cust:{r['Customer_ID']}"
            prod = f"prod:{r['Product_ID']}"
            if cust in self.G and prod in self.G:
                self._rel(cust, prod, f"bought ({r['times']}x, ${r['total']:.0f})")

        # Ship mode usage
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
        if eid in self.G:
            return dict(self.G.nodes[eid])
        return None

    def search_entities(self, query_str, etype=None, limit=50):
        results = []
        q = query_str.lower()
        for nid, attrs in self.G.nodes(data=True):
            if etype and attrs.get("type") != etype:
                continue
            name = attrs.get("name", "").lower()
            if q in nid.lower() or q in name:
                results.append((nid, dict(attrs)))
        return results[:limit]

    def get_neighbors(self, eid, max_nodes=100):
        if eid not in self.G:
            return [], []
        edges = list(self.G.edges(eid, data=True))
        nodes = []
        for src, dst, data in edges:
            label = data.get("label", "")
            if src == eid:
                nodes.append((dst, dict(self.G.nodes[dst]), label))
            else:
                nodes.append((src, dict(self.G.nodes[src]), label))
        return nodes[:max_nodes]

    def get_symbols(self):
        return dict(SYMBOL_DICT)

    def get_entity_types(self):
        types = set()
        for _, attrs in self.G.nodes(data=True):
            t = attrs.get("type")
            if t:
                types.add(t)
        return sorted(types)

    def get_type_count(self):
        counts = {}
        for _, attrs in self.G.nodes(data=True):
            t = attrs.get("type", "Unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def get_all_of_type(self, etype, limit=500):
        results = []
        for nid, attrs in self.G.nodes(data=True):
            if attrs.get("type") == etype:
                results.append((nid, dict(attrs)))
            if len(results) >= limit:
                break
        return results


if __name__ == "__main__":
    kb = KnowledgeBase()
    print(f"Graph: {kb.G.number_of_nodes()} nodes, {kb.G.number_of_edges()} edges")
    for t, c in sorted(kb.get_type_count().items()):
        print(f"  {t}: {c}")
    print(f"\nSymbols: {kb.get_symbols()}")
