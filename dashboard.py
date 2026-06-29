import sqlite3
import subprocess
import sys
import os
import random
import json
from dataclasses import dataclass
from typing import Optional, List

import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Superstore Enterprise Intelligence", layout="wide",
                    initial_sidebar_state="expanded", page_icon="📊")



DB = "superstore.db"
CLUSTER_CSV = "customer_clusters.csv"
METRICS_JSON = "cluster_metrics.json"
CLUSTER_CENTERS_CSV = "cluster_centers.csv"
MODEL_PKL = "kmeans_model.pkl"


@st.cache_resource
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


@st.cache_data(ttl=60)
def query(sql: str, params: tuple = ()):
    return pd.read_sql_query(sql, get_conn(), params=params)


@st.cache_data(ttl=60)
def load_clusters():
    try:
        return pd.read_csv(CLUSTER_CSV)
    except FileNotFoundError:
        return None


@st.cache_data(ttl=60)
def load_rules():
    return pd.read_csv("minedrules.csv")


@st.cache_data(ttl=300)
def load_cluster_metrics():
    try:
        with open(METRICS_JSON) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"silhouette_score": None}


@st.cache_data(ttl=300)
def load_cluster_centers():
    try:
        return pd.read_csv(CLUSTER_CENTERS_CSV)
    except FileNotFoundError:
        return None


@st.cache_data(ttl=300)
def get_bounds():
    dates = query("SELECT MIN(Order_Date) min_dt, MAX(Order_Date) max_dt FROM orders")
    segments = query("SELECT DISTINCT Segment FROM customers ORDER BY Segment")["Segment"].tolist()
    regions = query("SELECT DISTINCT Region FROM locations ORDER BY Region")["Region"].tolist()
    customers = query("SELECT Customer_ID, Customer_Name FROM customers ORDER BY Customer_Name")
    categories = query("SELECT Category_Name FROM categories ORDER BY Category_Name")["Category_Name"].tolist()
    subcats = query("SELECT Sub_Category_Name FROM sub_categories ORDER BY Sub_Category_Name")["Sub_Category_Name"].tolist()
    return {
        "min_dt": pd.Timestamp(dates["min_dt"].iloc[0]),
        "max_dt": pd.Timestamp(dates["max_dt"].iloc[0]),
        "segments": segments,
        "regions": regions,
        "customers": customers,
        "categories": categories,
        "subcategories": subcats,
    }


STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}

COLOR_MAP = {"VIP Customers": "#E63946", "Regular Customers": "#457B9D",
             "Medium Value Customers": "#2A9D8F", "Occasional Customers": "#E9C46A"}

CLUSTER_DESCRIPTIONS = {
    "VIP Customers": "High-spending, frequent buyers who generate the most profit. Prioritize retention and exclusive offers.",
    "Regular Customers": "Steady, reliable purchasers with consistent order patterns. Ideal for loyalty programs and cross-selling.",
    "Medium Value Customers": "Moderate spenders with room to grow. Target with upsell campaigns and personalized recommendations.",
    "Occasional Customers": "Infrequent, low-value buyers. Re-engage with reactivation campaigns and entry-level product offers.",
}


# ────────────────────────────────────────────────────────────────────────
# INFO TOOLTIP HELPER
# ────────────────────────────────────────────────────────────────────────

def info(text):
    return f'<span title="{text}" style="cursor:help; color:#888; font-size:15px; margin-left:4px">ⓘ</span>'


def metric_card(label, value, help_text):
    st.markdown(f"**{label}** {info(help_text)}", unsafe_allow_html=True)
    st.metric(" ", value, label_visibility="collapsed")


# ────────────────────────────────────────────────────────────────────────
# FILTER FRAMEWORK
# ────────────────────────────────────────────────────────────────────────

@dataclass
class Filters:
    start_date: object
    end_date: object
    segments: List[str]
    regions: List[str]
    customer_id: Optional[str]
    customer_name: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]
    all_segments: List[str]
    all_regions: List[str]

    def where(self, has_customers=True, has_locations=True, alias_o="o", alias_c="c", alias_l="l"):
        clauses = [f"{alias_o}.Order_Date BETWEEN ? AND ?"]
        params = [str(self.start_date.date()), str(self.end_date.date())]

        if has_customers and self.segments and len(self.segments) < len(self.all_segments):
            placeholders = ",".join(["?"] * len(self.segments))
            clauses.append(f"{alias_c}.Segment IN ({placeholders})")
            params.extend(self.segments)

        if has_locations and self.regions and len(self.regions) < len(self.all_regions):
            placeholders = ",".join(["?"] * len(self.regions))
            clauses.append(f"{alias_l}.Region IN ({placeholders})")
            params.extend(self.regions)

        if self.customer_id:
            clauses.append(f"{alias_o}.Customer_ID = ?")
            params.append(self.customer_id)

        return " AND ".join(clauses), params

    def active_chips(self):
        chips = [f"📅 {self.start_date.date()} → {self.end_date.date()}"]
        if self.segments and len(self.segments) < len(self.all_segments):
            chips.append("🏷️ " + ", ".join(self.segments))
        if self.regions and len(self.regions) < len(self.all_regions):
            chips.append("🌎 " + ", ".join(self.regions))
        if self.customer_name:
            chips.append(f"👤 {self.customer_name}")
        if self.category:
            chips.append(f"📦 {self.category}")
        if self.subcategory:
            chips.append(f"📦 {self.subcategory}")
        return chips

    def is_default(self):
        return (not self.customer_id
                and not self.category
                and not self.subcategory
                and len(self.segments) == len(self.all_segments)
                and len(self.regions) == len(self.all_regions))


def render_sidebar() -> str:
    st.sidebar.title("Superstore Intelligence")
    with st.sidebar.expander("📖 Dashboard Guide", expanded=False):
        st.markdown("""
        ### 🎯 What is this?
        **Superstore Intelligence** is an enterprise analytics system that combines
        **traditional BI**, **AI-powered customer clustering**, and **Symbolic AI rules**
        — all in one dashboard. It helps executives, analysts, and judges explore
        sales data, understand customer behavior, and generate actionable marketing
        recommendations.

        ---
        ### 🧭 How to navigate
        Use the **menu below** to switch between pages. Each page focuses on a
        different business question.

        ---
        ### 🎛️ Using filters
        The **filter bar** at the top of every page lets you narrow down data by:
        - **📅 Period** — select a date range
        - **🏷️ Customer type** — Consumer, Corporate, or Home Office
        - **🌎 Region** — East, Central, West, South
        - **📦 Category** — Furniture, Office Supplies, Technology
        - **👤 Customer** — pick a specific person

        Filters affect **every chart and table** on the current page.

        ---
        ### 📄 Page guide

        | Page | What it shows |
        |------|---------------|
        | **Executive Overview** | KPIs, revenue trends, CLV, category & segment breakdown |
        | **US Map** | Geographic revenue/transaction heatmap by state |
        | **Supply Chain** | Warehouse loads, carrier delays, inventory levels |
        | **Clustered AI** | K-Means customer profiles (VIP, Regular, Medium, Occasional) |
        | **Marketing Campaigns** | Actionable rules from Symbolic AI grouped by campaign type |
        | **Per-Product Segments** | Which customer profiles buy each product/line |
        | **Symbolic AI Rules** | Browse all 816 mined rules with lift/support filters |
        | **Add Customer** | Judge tool — insert test customers and trigger AI recompute |
        | **Data Integrity** | Data quality issues found during EDA |

        ---
        ### 🔍 Tips
        - **Hover** the ⓘ icons next to metrics for explanations
        - Use the **"Reset all"** button to clear filters quickly
        - After **adding a customer**, the AI pipeline recomputes automatically
        - The **Marketing Campaigns** page uses real mined rules — try each
          campaign type to see different AI recommendations

        ---
        ### ⚙️ Technical
        - **K-Means** clusters 794 customers into 4 profiles using 4 features
          (total spend, order count, avg order value, purchase frequency)
        - **Silhouette Score**: 0.34 (meaningful separation between clusters)
        - **Symbolic AI** mined 816 rules from 15 strategies with lift up to 40+
        - All data sourced from `superstore.db` (4,916 orders, 1,892 products)
        """)
    return st.sidebar.radio("Menu", [
        "Executive Overview", "US Map", "Supply Chain",
        "Clustered AI", "Marketing Campaigns",
        "Per-Product Segments", "Symbolic AI Rules",
        "Add Customer", "Data Integrity",
    ], key="nav_page")


def render_top_filters():
    bounds = get_bounds()

    header_col, reset_col = st.columns([6, 1])
    with header_col:
        st.markdown("### Filters")
    with reset_col:
        if st.button("Reset all", width="stretch"):
            for k in ("f_daterange", "f_segment", "f_region", "f_customer", "f_category", "f_subcategory"):
                st.session_state.pop(k, None)
            st.rerun()

    cols = st.columns([2, 2, 1.5, 1.5, 2])

    with cols[0]:
        dr = st.date_input("Period", [bounds["min_dt"], bounds["max_dt"]],
                           min_value=bounds["min_dt"], max_value=bounds["max_dt"],
                           key="f_daterange", label_visibility="collapsed")
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start_dt, end_dt = pd.Timestamp(dr[0]), pd.Timestamp(dr[1])
    else:
        start_dt, end_dt = bounds["min_dt"], bounds["max_dt"]

    with cols[1]:
        segs = st.multiselect("Customer type", bounds["segments"],
                               default=bounds["segments"], key="f_segment", label_visibility="collapsed")
    with cols[2]:
        regions = st.multiselect("Region", bounds["regions"],
                                  default=bounds["regions"], key="f_region", label_visibility="collapsed")
    with cols[3]:
        cat_opts = ["All"] + bounds["categories"]
        sel_cat = st.selectbox("Category", cat_opts, key="f_category", label_visibility="collapsed")
    with cols[4]:
        names = ["All customers"] + bounds["customers"]["Customer_Name"].tolist()
        sel_name = st.selectbox("Customer", names, key="f_customer", label_visibility="collapsed")

    if sel_name != "All customers":
        cust_id = bounds["customers"].loc[
            bounds["customers"]["Customer_Name"] == sel_name, "Customer_ID"
        ].iloc[0]
    else:
        cust_id, sel_name = None, None
    if sel_cat != "All":
        subcat_opts = ["All"] + bounds["subcategories"]
        sel_subcat = st.selectbox("Sub-category", subcat_opts, key="f_subcategory", label_visibility="collapsed")
    else:
        sel_subcat = None

    filters = Filters(
        start_date=start_dt, end_date=end_dt,
        segments=segs or bounds["segments"],
        regions=regions or bounds["regions"],
        customer_id=cust_id, customer_name=sel_name,
        category=sel_cat if sel_cat != "All" else None,
        subcategory=sel_subcat if sel_subcat and sel_subcat != "All" else None,
        all_segments=bounds["segments"], all_regions=bounds["regions"],
    )

    if not filters.is_default():
        st.info(" · ".join(filters.active_chips()))
    else:
        st.caption("All data · " + filters.active_chips()[0])

    return filters


def kpi(filters: Filters):
    where, params = filters.where(has_customers=True, has_locations=True)
    sql = f"""
        SELECT COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales), 0) AS revenue,
               ROUND(SUM(od.Sales) / COUNT(DISTINCT o.Order_ID), 2) AS avg_order_value,
               COUNT(DISTINCT o.Customer_ID) AS customers,
               ROUND(SUM(od.Sales) / COUNT(DISTINCT o.Customer_ID), 2) AS avg_clv
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE {where}
    """
    return query(sql, tuple(params)).iloc[0]


# ────────────────────────────────────────────────────────────────────────
# RENDER
# ────────────────────────────────────────────────────────────────────────

page = render_sidebar()

st.title(page)

filters = render_top_filters()

st.divider()

# ════════════════════════════════════════════════════════════════════════
# PAGE: Executive Overview
# ════════════════════════════════════════════════════════════════════════
if page == "Executive Overview":
    k = kpi(filters)
    cols = st.columns(4)
    with cols[0]:
        metric_card("Total Revenue", f"${k.revenue:,.0f}",
                     "Net sales revenue across all orders in the selected period")
    with cols[1]:
        metric_card("Transactions", f"{k.orders:,}",
                     "Total number of customer orders placed")
    with cols[2]:
        metric_card("Avg Customer LTV (CLV)", f"${k.avg_clv:,.0f}",
                     "Customer Lifetime Value — average total revenue per customer over their entire history with the company")
    with cols[3]:
        metric_card("Active Customers", f"{k.customers:,}",
                     "Distinct customers who placed at least one order in the period")

    where, params = filters.where(has_customers=True, has_locations=True)

    trend = query(f"""
        SELECT strftime('%Y-%m', o.Order_Date) AS ym, ROUND(SUM(od.Sales), 0) AS revenue
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE {where}
        GROUP BY ym ORDER BY ym
    """, tuple(params))
    fig = px.bar(trend, x="ym", y="revenue", title="Monthly Revenue Trend", height=350)
    fig.update_layout(xaxis_tickangle=-60, margin=dict(l=20, r=20, t=40, b=40))
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    cat = query(f"""
        SELECT cat.Category_Name AS category, ROUND(SUM(od.Sales), 0) AS revenue
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        WHERE {where}
        GROUP BY cat.Category_Name
    """, tuple(params))
    fig = px.pie(cat, values="revenue", names="category",
                 title="Revenue by Product Category", hole=0.4, height=350)
    c1.plotly_chart(fig, width="stretch")

    seg = query(f"""
        SELECT c.Segment AS customer_type, ROUND(SUM(od.Sales), 0) AS revenue,
               COUNT(DISTINCT o.Order_ID) AS transactions
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE {where}
        GROUP BY c.Segment
    """, tuple(params))
    fig = px.bar(seg, x="customer_type", y=["revenue", "transactions"], barmode="group",
                 title="Revenue & Transactions by Customer Type", height=350)
    c2.plotly_chart(fig, width="stretch")

    with st.expander("📊 Top product lines"):
        subcat = query(f"""
            SELECT sc.Sub_Category_Name AS product_line, cat.Category_Name AS category,
                   ROUND(SUM(od.Sales), 0) AS revenue
            FROM orders o
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN customers c ON c.Customer_ID = o.Customer_ID
            JOIN locations l ON l.Postal_Code = o.Postal_Code
            JOIN products p ON p.Product_ID = od.Product_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
            WHERE {where}
            GROUP BY sc.Sub_Category_Name
            ORDER BY revenue DESC LIMIT 10
        """, tuple(params))
        fig = px.bar(subcat, x="revenue", y="product_line", color="category",
                     orientation="h", title="Top 10 Product Lines by Revenue", height=350)
        st.plotly_chart(fig, width="stretch")

    st.subheader("💰 Customer Lifetime Value (CLV)")
    c1, c2 = st.columns(2)
    clv_by_segment = query(f"""
        SELECT c.Segment AS customer_type,
               COUNT(DISTINCT c.Customer_ID) AS customer_count,
               ROUND(SUM(od.Sales), 0) AS total_revenue,
               ROUND(SUM(od.Sales) / COUNT(DISTINCT c.Customer_ID), 0) AS avg_clv
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE {where}
        GROUP BY c.Segment
    """, tuple(params))
    fig = px.bar(clv_by_segment, x="customer_type", y="avg_clv",
                 title="Avg CLV by Customer Type", height=350,
                 text_auto="$,.0f", color="customer_type",
                 color_discrete_sequence=px.colors.qualitative.Set2)
    c1.plotly_chart(fig, width="stretch")

    clusters_clv = load_clusters()
    if clusters_clv is not None:
        display = clusters_clv.copy()
        if len(filters.segments) < len(filters.all_segments):
            display = display[display["Segment"].isin(filters.segments)]
        clv_by_profile = display.groupby("Cluster_Name").agg(
            customer_count=("Customer_ID", "count"),
            avg_clv=("Customer_Total_Sales", "mean"),
        ).round(0).reset_index().rename(columns={"Cluster_Name": "profile"})
        fig = px.bar(clv_by_profile, x="profile", y="avg_clv",
                     title="Avg CLV by AI Profile", height=350,
                     text_auto="$,.0f", color="profile",
                     color_discrete_map=COLOR_MAP)
        c2.plotly_chart(fig, width="stretch")

    with st.expander("📋 CLV details by customer"):
        if clusters_clv is not None:
            display_all = clusters_clv[["Customer_Name", "Segment", "Cluster_Name",
                                        "Customer_Total_Sales", "Customer_Order_Count",
                                        "Average_Order_Value"]].rename(columns={
                "Segment": "Customer Type", "Cluster_Name": "AI Profile",
                "Customer_Total_Sales": "CLV (Total Spend)",
                "Customer_Order_Count": "Orders", "Average_Order_Value": "Avg Order Value",
            }).sort_values("CLV (Total Spend)", ascending=False)
            if len(filters.segments) < len(filters.all_segments):
                display_all = display_all[display_all["Customer Type"].isin(filters.segments)]
            st.dataframe(display_all, width="stretch", hide_index=True)

# ════════════════════════════════════════════════════════════════════════
# PAGE: US Map
# ════════════════════════════════════════════════════════════════════════
elif page == "US Map":
    where, params = filters.where(has_customers=True, has_locations=True)

    by_state = query(f"""
        SELECT l.State, l.Region,
               ROUND(SUM(od.Sales), 0) AS revenue,
               COUNT(DISTINCT o.Order_ID) AS transactions,
               COUNT(DISTINCT c.Customer_ID) AS active_customers,
               ROUND(AVG(od.Sales), 2) AS avg_revenue
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE {where}
        GROUP BY l.State
    """, tuple(params))
    by_state["abbr"] = by_state["State"].map(STATE_ABBR)

    metric = st.selectbox("Business measure",
                           ["revenue", "transactions", "active_customers", "avg_revenue"], index=0)
    label_map = {"revenue": "Revenue", "transactions": "Transactions",
                 "active_customers": "Active Customers", "avg_revenue": "Avg Revenue"}

    col1, col2 = st.columns([3, 1])
    with col1:
        fig = px.choropleth(by_state, locations="abbr", locationmode="USA-states",
                            color=metric, scope="usa",
                            title=f"{label_map[metric]} by State",
                            color_continuous_scale="Blues",
                            hover_data={"State": True, metric: True, "abbr": False})
        fig.update_layout(height=600, margin=dict(l=0, r=0, t=40, b=0))
        fig.update_geos(showframe=False, showcoastlines=False, projection_type="albers usa")
        st.plotly_chart(fig, width="stretch")
    with col2:
        top10 = by_state.sort_values(metric, ascending=False).head(10)
        for i in range(min(5, len(top10))):
            row = top10.iloc[i]
            val = row[metric]
            formatted = f"${val:,.0f}" if metric in ("revenue", "avg_revenue") else f"{val:,}"
            st.metric(f"#{i+1} {row['State']}", formatted)

    with st.expander("🏙️ Top cities"):
        city = query(f"""
            SELECT l.City, l.State, ROUND(SUM(od.Sales), 0) AS revenue
            FROM orders o
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN customers c ON c.Customer_ID = o.Customer_ID
            JOIN locations l ON l.Postal_Code = o.Postal_Code
            WHERE {where}
            GROUP BY l.City
            HAVING SUM(od.Sales) > 1000
            ORDER BY revenue DESC LIMIT 20
        """, tuple(params))
        st.dataframe(city, width="stretch", hide_index=True)

# ════════════════════════════════════════════════════════════════════════
# PAGE: Supply Chain
# ════════════════════════════════════════════════════════════════════════
elif page == "Supply Chain":
    warehouses = query("SELECT * FROM warehouses")
    carriers = query("SELECT * FROM carriers")

    c1, c2 = st.columns(2)
    fig = px.bar(warehouses, x="warehouse_name", y=["current_load", "capacity"],
                 barmode="group", title="Warehouse Capacity vs Current Load",
                 height=350, labels={"value": "Units", "variable": "Metric"})
    c1.plotly_chart(fig, width="stretch")

    fig = px.bar(warehouses, x="warehouse_name", y=["staff_on_shift", "loading_queue"],
                 barmode="group", title="Staff Availability vs Queue by Warehouse",
                 height=350, labels={"value": "Count", "variable": "Metric"})
    c2.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    fig = px.bar(carriers, x="carrier_name", y="avg_delay_days",
                 title="Average Carrier Delay (Days)", height=350,
                 color="carrier_name", text_auto=".1f")
    c1.plotly_chart(fig, width="stretch")

    fig = px.bar(carriers, x="carrier_name", y="active_trucks",
                 title="Active Fleet by Carrier", height=350,
                 color="carrier_name", text_auto=",")
    c2.plotly_chart(fig, width="stretch")

    with st.expander("📦 Inventory levels"):
        region_options = ["All"] + sorted(set(filters.regions) | {r for r in warehouses["region"].unique()})
        sel_region = st.selectbox("Warehouse Region", region_options, key="inv_region")
        inv_sql = """
            SELECT w.warehouse_name, w.region, p.Product_Name, sc.Sub_Category_Name,
                   i.stock, i.reserved, i.incoming
            FROM inventory i
            JOIN warehouses w ON w.warehouse_id = i.warehouse_id
            JOIN products p ON p.Product_ID = i.product_id
            JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
            WHERE 1=1
        """
        inv_params = []
        if sel_region != "All":
            inv_sql += " AND w.region = ?"
            inv_params.append(sel_region)
        elif len(filters.regions) < len(filters.all_regions):
            placeholders = ",".join(["?"] * len(filters.regions))
            inv_sql += f" AND w.region IN ({placeholders})"
            inv_params.extend(filters.regions)
        inv_sql += " ORDER BY i.stock DESC LIMIT 200"
        inventory = query(inv_sql, tuple(inv_params))
        st.dataframe(inventory, width="stretch", hide_index=True)

    with st.expander("🚚 Delivery delay diagnosis"):
        where, params = filters.where(has_customers=False, has_locations=True)
        delay_data = query(f"""
            SELECT l.Region, w.warehouse_name,
                   AVG(julianday(o.Ship_Date) - julianday(o.Order_Date)) AS avg_delay_days,
                   COUNT(*) AS order_count,
                   w.current_load, w.staff_on_shift, w.loading_queue
            FROM orders o
            JOIN locations l ON l.Postal_Code = o.Postal_Code
            JOIN warehouses w ON w.region = l.Region
            WHERE {where}
            GROUP BY l.Region, w.warehouse_name
        """, tuple(params))
        fig = px.scatter(delay_data, x="avg_delay_days", y="current_load",
                         size="order_count", color="Region",
                         hover_data=["warehouse_name", "staff_on_shift", "loading_queue"],
                         title="Fulfillment Delay vs Warehouse Load by Region",
                         height=400,
                         labels={"avg_delay_days": "Avg Delay (Days)", "current_load": "Warehouse Load"})
        st.plotly_chart(fig, width="stretch")

    with st.expander("🏭 Warehouse routing recommendations"):
        routing = query("""
            SELECT l.State, l.Region, w.warehouse_name, w.city AS warehouse_city,
                   w.current_load, w.capacity,
                   ROUND(100.0 * w.current_load / w.capacity, 1) AS load_pct
            FROM locations l
            JOIN warehouses w ON w.region = l.Region
            GROUP BY l.State
        """)
        routing["available_capacity"] = routing["capacity"] - routing["current_load"]
        routing["status"] = routing["load_pct"].apply(
            lambda p: "✅ Available" if p < 80 else ("⚠️ Near capacity" if p < 95 else "❌ At capacity")
        )
        if len(filters.regions) < len(filters.all_regions):
            routing = routing[routing["Region"].isin(filters.regions)]
        st.dataframe(routing.drop_duplicates(subset="State").sort_values("load_pct"),
                     width="stretch", hide_index=True)

# ════════════════════════════════════════════════════════════════════════
# PAGE: Clustered AI
# ════════════════════════════════════════════════════════════════════════
elif page == "Clustered AI":
    clusters = load_clusters()
    metrics = load_cluster_metrics()
    centers = load_cluster_centers()
    if clusters is None:
        st.warning("Run `python run_pipeline.py` first to generate customer clusters.")
        st.stop()

    sil = metrics.get("silhouette_score")
    st.markdown(
        f"**K-Means clustering** segments {len(clusters)} customers into 4 distinct profiles "
        f"based on purchasing patterns. "
        + (f"Model quality (Silhouette Score): **{sil}** " + info(
            "Ranges from -1 to 1. Values above 0.3 indicate meaningful separation between clusters."
        ) if sil else "")
        + " — higher is better.",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("### Customer Profiles")
        prof_cols = st.columns(4)
        for i, (name, desc) in enumerate(CLUSTER_DESCRIPTIONS.items()):
            count = len(clusters[clusters["Cluster_Name"] == name])
            pct = count / len(clusters) * 100
            with prof_cols[i]:
                st.markdown(f"**{name}**")
                st.markdown(f"*{count} customers ({pct:.0f}%)*")
                st.caption(desc)

    c1, c2 = st.columns(2)
    counts = clusters["Cluster_Name"].value_counts().reset_index()
    counts.columns = ["Cluster_Name", "Count"]
    fig = px.pie(counts, values="Count", names="Cluster_Name",
                 title="Customer Profile Distribution", hole=0.4,
                 color="Cluster_Name", color_discrete_map=COLOR_MAP)
    c1.plotly_chart(fig, width="stretch")

    if centers is not None:
        c2.dataframe(
            centers[["Cluster_Name", "Customer_Total_Sales", "Customer_Order_Count",
                      "Average_Order_Value", "Purchase_Frequency"]].rename(columns={
                "Cluster_Name": "Profile", "Customer_Total_Sales": "Avg CLV",
                "Customer_Order_Count": "Avg Orders", "Average_Order_Value": "Avg Order Value",
                "Purchase_Frequency": "Orders/Year",
            }).round(1),
            width="stretch", hide_index=True,
        )

    with st.expander("📈 Customer profile visualization (PCA)"):
        axis_opts = ["Customer_Total_Sales", "Customer_Order_Count", "Average_Order_Value", "Purchase_Frequency"]
        cols = st.columns(2)
        x_axis = cols[0].selectbox("X dimension", axis_opts, index=0)
        y_axis = cols[1].selectbox("Y dimension", axis_opts, index=1)
        clusters_subset = clusters.copy()
        if len(filters.segments) < len(filters.all_segments):
            clusters_subset = clusters_subset[clusters_subset["Segment"].isin(filters.segments)]
        fig = px.scatter(clusters_subset, x=x_axis, y=y_axis, color="Cluster_Name",
                         color_discrete_map=COLOR_MAP,
                         hover_data=["Customer_Name", "Segment", "Cluster_Name"],
                         title=f"{x_axis} vs {y_axis} by Customer Profile",
                         height=500, opacity=0.6)
        st.plotly_chart(fig, width="stretch")

    with st.expander("📋 All customers with AI profile assignments"):
        display = clusters[["Customer_ID", "Customer_Name", "Segment", "Cluster_Name",
                            "Customer_Total_Sales", "Customer_Order_Count"]].rename(columns={
            "Segment": "Customer Type", "Cluster_Name": "AI Profile",
            "Customer_Total_Sales": "Total Spend", "Customer_Order_Count": "Orders",
        })
        if len(filters.segments) < len(filters.all_segments):
            display = display[display["Customer Type"].isin(filters.segments)]
        st.dataframe(display, width="stretch", hide_index=True)

    with st.expander("💡 Business recommendations"):
        for name in ["VIP Customers", "Regular Customers", "Medium Value Customers", "Occasional Customers"]:
            count = len(clusters[clusters["Cluster_Name"] == name])
            with st.container(border=True):
                st.markdown(f"**{name}** ({count} customers)")
                recs = {
                    "VIP Customers": "Launch an exclusive VIP loyalty program with early access to new products and dedicated support.",
                    "Regular Customers": "Introduce a points-based rewards system and personalized product recommendations via email.",
                    "Medium Value Customers": "Run targeted upsell campaigns — offer bundle deals and volume discounts to increase order value.",
                    "Occasional Customers": "Send re-engagement emails with limited-time discounts and highlight best-selling products.",
                }
                st.markdown(f"👉 {recs.get(name, '')}")

# ════════════════════════════════════════════════════════════════════════
# PAGE: Marketing Campaigns
# ════════════════════════════════════════════════════════════════════════
elif page == "Marketing Campaigns":
    st.markdown(
        "**Symbolic AI** mined **816 validated rules** from transaction data. "
        "Each rule below is a ready-to-use marketing insight with a quantifiable lift.",
        unsafe_allow_html=True,
    )
    rules = load_rules()
    campaign_types = {
        "Cross-sell": ["combo_product", "subcategory_complement", "subcat_cross_recommend"],
        "Upsell": ["subcategory_product", "segment_subcategory", "segment_pricetier"],
        "Seasonal": ["seasonal"],
        "Regional campaign": ["region_subcategory", "segment_region_subcategory"],
        "VIP retention": ["clv_subcategory", "recency_subcategory", "customer_similarity"],
    }

    camp = st.selectbox("Campaign type", list(campaign_types.keys()))
    type_filter = campaign_types[camp]
    filtered = rules[rules["Type"].isin(type_filter)].sort_values("Lift", ascending=False).head(20)

    st.markdown(f"**{camp}** — {len(filtered)} actionable recommendations from Symbolic AI")
    st.caption(
        f"Lift measures how much more likely the consequent is when the antecedent holds. "
        f"Lift > 1 means positive correlation. Higher = stronger recommendation."
    )

    for _, rule in filtered.iterrows():
        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(f"**{rule['Antecedent']}** → **{rule['Consequent']}**")
                if pd.notna(rule.get("Explanation")):
                    st.caption(rule["Explanation"])
            with cols[1]:
                st.markdown(f"Lift: **{rule['Lift']:.1f}**")
                st.caption(f"Support: {rule['Support']:.4f}")
            with cols[2]:
                action_map = {
                    "combo_product": "Bundle & cross-sell",
                    "subcategory_complement": "Recommend complementary",
                    "subcat_cross_recommend": "Cross-suggest",
                    "subcategory_product": "Feature top product",
                    "segment_subcategory": "Segment-specific campaign",
                    "segment_pricetier": "Tiered pricing offer",
                    "seasonal": "Seasonal promotion",
                    "region_subcategory": "Regional push",
                    "segment_region_subcategory": "Targeted regional segment",
                    "clv_subcategory": "VIP exclusive",
                    "recency_subcategory": "Re-activation",
                    "customer_similarity": "Look-alike targeting",
                }
                st.markdown(f"**{action_map.get(rule['Type'], 'Promote')}**")

# ════════════════════════════════════════════════════════════════════════
# PAGE: Per-Product Segments
# ════════════════════════════════════════════════════════════════════════
elif page == "Per-Product Segments":
    clusters = load_clusters()
    if clusters is None:
        st.warning("Run `python run_pipeline.py` first.")
        st.stop()

    analysis_level = st.radio("Analyze by", ["Category", "Product Line", "Product"], horizontal=True)

    if analysis_level == "Category":
        items = query("SELECT Category_Name FROM categories ORDER BY Category_Name")["Category_Name"].tolist()
        sel = st.selectbox("Category", items)
        sql, p = ("""
            SELECT DISTINCT c.Customer_ID
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN products pr ON pr.Product_ID = od.Product_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = pr.Sub_Category_ID
            JOIN categories cat ON cat.Category_ID = sc.Category_ID
            JOIN locations l ON l.Postal_Code = o.Postal_Code
            WHERE cat.Category_Name = ?
        """, [sel])
    elif analysis_level == "Product Line":
        items = query("SELECT Sub_Category_Name FROM sub_categories ORDER BY Sub_Category_Name")["Sub_Category_Name"].tolist()
        sel = st.selectbox("Product Line", items)
        sql, p = ("""
            SELECT DISTINCT c.Customer_ID
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN products pr ON pr.Product_ID = od.Product_ID
            JOIN sub_categories sc ON sc.Sub_Category_ID = pr.Sub_Category_ID
            JOIN locations l ON l.Postal_Code = o.Postal_Code
            WHERE sc.Sub_Category_Name = ?
        """, [sel])
    else:
        items = query("SELECT Product_ID, Product_Name FROM products ORDER BY Product_Name")
        sel_name = st.selectbox("Product", items["Product_Name"].tolist())
        sel_id = items.loc[items["Product_Name"] == sel_name, "Product_ID"].iloc[0]
        sel = sel_name
        sql, p = ("""
            SELECT DISTINCT c.Customer_ID
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            JOIN locations l ON l.Postal_Code = o.Postal_Code
            WHERE od.Product_ID = ?
        """, [sel_id])

    where, where_params = filters.where(has_customers=False, has_locations=True)
    sql += f" AND {where}"
    p.extend(where_params)

    buying_customers = query(sql, tuple(p))
    merged = buying_customers.merge(clusters[["Customer_ID", "Cluster_Name", "Segment"]], on="Customer_ID", how="left")
    if len(filters.segments) < len(filters.all_segments):
        merged = merged[merged["Segment"].isin(filters.segments)]

    c1, c2 = st.columns(2)
    counts = merged["Cluster_Name"].value_counts().reset_index()
    counts.columns = ["Cluster_Name", "Count"]
    fig = px.pie(counts, values="Count", names="Cluster_Name",
                 title=f"Customer Profiles Buying {sel}",
                 hole=0.4, color="Cluster_Name", color_discrete_map=COLOR_MAP)
    c1.plotly_chart(fig, width="stretch")

    seg_counts = merged.groupby(["Cluster_Name", "Segment"]).size().reset_index(name="Count")
    fig = px.bar(seg_counts, x="Cluster_Name", y="Count", color="Segment",
                 title=f"Customer Type Breakdown — {sel}", barmode="group", height=400)
    c2.plotly_chart(fig, width="stretch")

# ════════════════════════════════════════════════════════════════════════
# PAGE: Symbolic AI Rules
# ════════════════════════════════════════════════════════════════════════
elif page == "Symbolic AI Rules":
    st.markdown(
        "**816 validated rules** mined from the Superstore knowledge base. "
        "Use the filters below to explore — higher Lift means stronger correlation.",
        unsafe_allow_html=True,
    )

    rules = load_rules()

    c1, c2, c3 = st.columns(3)
    rule_types = ["All"] + sorted(rules["Type"].unique().tolist())
    sel_type = c1.selectbox("Rule type", rule_types)
    min_lift = c2.slider("Minimum Lift", 0.0, float(rules["Lift"].max()), 0.0, 0.5)
    min_support = c3.slider("Minimum Support", 0.0, float(rules["Support"].max()), 0.0, 0.001)

    filtered = rules.copy()
    if sel_type != "All":
        filtered = filtered[filtered["Type"] == sel_type]
    filtered = filtered[(filtered["Lift"] >= min_lift) & (filtered["Support"] >= min_support)]
    filtered = filtered.sort_values("Lift", ascending=False)

    st.caption(f"{len(filtered):,} of {len(rules):,} rules match")
    st.dataframe(filtered[["RuleID", "Type", "Antecedent", "Consequent", "Lift", "Support", "Explanation"]],
                 width="stretch", hide_index=True)

    with st.expander("📊 Rule type distribution"):
        type_counts = rules["Type"].value_counts().reset_index()
        type_counts.columns = ["Type", "Count"]
        fig = px.bar(type_counts, x="Type", y="Count", title="Rules by Type", height=400,
                     color="Count", color_continuous_scale="Viridis")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, width="stretch")

# ════════════════════════════════════════════════════════════════════════
# PAGE: Add Customer
# ════════════════════════════════════════════════════════════════════════
elif page == "Add Customer":
    st.markdown("Add a new customer record. The AI pipeline automatically recomputes to include the new data.")

    with st.form("add_customer_form"):
        col1, col2 = st.columns(2)
        cust_name = col1.text_input("Customer Name", "New Customer")
        segment = col2.selectbox("Customer Type", ["Consumer", "Corporate", "Home Office"])
        city = col1.text_input("City", "New York")
        state = col2.text_input("State", "New York")
        postal_code = col1.text_input("Postal Code", "10001")
        region = col2.selectbox("Region", ["East", "Central", "West", "South"])

        st.markdown("---")
        st.markdown("**Optional: Add a transaction**")
        add_order = st.checkbox("Also add an order")
        prod_id, sales_amt, ship_mode = None, 100.0, "Standard Class"
        if add_order:
            products = query("SELECT Product_ID, Product_Name FROM products ORDER BY Product_Name")
            prod_name = st.selectbox("Product", products["Product_Name"].tolist())
            prod_id = products.loc[products["Product_Name"] == prod_name, "Product_ID"].iloc[0]
            sales_amt = st.number_input("Sale Amount ($)", min_value=0.0, value=100.0, step=10.0)
            ship_mode = st.selectbox("Shipping Method", ["Standard Class", "Second Class", "First Class", "Same Day"])

        submitted = st.form_submit_button("Add & Recompute AI Pipeline")

    if submitted:
        conn = get_conn()
        cur = conn.cursor()
        cust_id = f"JD-{random.randint(10000, 99999)}"
        try:
            cur.execute("INSERT INTO customers (Customer_ID, Customer_Name, Segment) VALUES (?, ?, ?)",
                        (cust_id, cust_name, segment))
            loc_exists = cur.execute("SELECT 1 FROM locations WHERE Postal_Code = ?", (float(postal_code),)).fetchone()
            if not loc_exists:
                cur.execute("INSERT INTO locations (Postal_Code, City, State, Country, Region) VALUES (?, ?, ?, 'United States', ?)",
                            (float(postal_code), city, state, region))
            if add_order:
                sm = query("SELECT Ship_Mode_ID FROM ship_modes WHERE Ship_Mode_Name = ?", (ship_mode,))
                ship_mode_id = sm["Ship_Mode_ID"].iloc[0]
                order_id = f"JD-{random.randint(100000, 999999)}"
                cur.execute(
                    "INSERT INTO orders (Order_ID, Order_Date, Ship_Date, Ship_Mode_ID, Customer_ID, Postal_Code) "
                    "VALUES (?, date('now'), date('now', '+2 days'), ?, ?, ?)",
                    (order_id, ship_mode_id, cust_id, float(postal_code))
                )
                cur.execute(
                    "INSERT INTO order_details (Order_ID, Product_ID, Sales) VALUES (?, ?, ?)",
                    (order_id, prod_id, sales_amt)
                )
            conn.commit()
            st.success(f"Customer **{cust_name}** (ID: {cust_id}) added!")

            with st.spinner("Recomputing AI pipeline..."):
                try:
                    result = subprocess.run(
                        [sys.executable, "run_pipeline.py"],
                        capture_output=True, text=True,
                        cwd=os.path.dirname(os.path.abspath(__file__))
                    )
                    if result.returncode == 0:
                        st.success("Pipeline recomputed. Refreshing dashboard...")
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.rerun()
                    else:
                        st.error(f"Pipeline error:\n{result.stderr}")
                except Exception as e:
                    st.info("Pipeline recompute not available on cloud deployment. The dashboard uses pre-computed data which is already up-to-date.")
        except Exception as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()

# ════════════════════════════════════════════════════════════════════════
# PAGE: Data Integrity
# ════════════════════════════════════════════════════════════════════════
elif page == "Data Integrity":
    st.markdown(
        "The original flat-file system let data entry errors through. "
        "Below are the issues discovered during data analysis — "
        "all resolvable with an input validation layer.",
        unsafe_allow_html=True,
    )

    issues = pd.read_csv("data_quality_examples.csv")

    for issue_name in issues["Issue"].unique():
        subset = issues[issues["Issue"] == issue_name].head(3)
        with st.expander(f"**{issue_name}** — {len(issues[issues['Issue'] == issue_name])} records affected"):
            for _, r in subset.iterrows():
                st.code(f"Row {r['RowID']}: {r['Value']}")
                st.caption(f"Expected: {r['ShouldBe']} | Context: {r['Context']}")
            if len(subset) > 3:
                st.caption(f"… and {len(subset) - 3} more")

    st.subheader("Duplicate Product IDs")
    col_data = query("""
        SELECT p.Product_ID, COUNT(*) AS variants, GROUP_CONCAT(p.Product_Name, ' | ') AS names
        FROM products p
        GROUP BY p.Product_ID
        HAVING COUNT(*) > 1
        LIMIT 10
    """)
    for _, r in col_data.iterrows():
        st.warning(f"**{r['Product_ID']}** → {r['variants']} names")
        for name in r['names'].split(" | "):
            st.markdown(f"- {name}")

    zip_data = query("""
        SELECT l.Postal_Code, l.City, l.State, COUNT(o.Order_ID) AS orders
        FROM locations l
        JOIN orders o ON o.Postal_Code = l.Postal_Code
        WHERE CAST(l.Postal_Code AS INTEGER) < 10000
        GROUP BY l.Postal_Code
        ORDER BY l.Postal_Code
        LIMIT 10
    """)
    if len(zip_data) > 0:
        with st.expander(f"**ZIP codes missing leading zero** — {len(zip_data)} affected"):
            for _, r in zip_data.iterrows():
                pc = int(r["Postal_Code"])
                st.code(f"Stored: {pc:04d} → Expected: {pc:05d} | {r['City']}, {r['State']} ({r['orders']} orders)")
