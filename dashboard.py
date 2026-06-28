import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Superstore BI Dashboard", layout="wide")

DB = "superstore.db"


@st.cache_resource
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


@st.cache_data
def query(sql):
    return pd.read_sql_query(sql, get_conn())


# ── Sidebar ──
st.sidebar.title("Superstore BI")
page = st.sidebar.radio("Navigate", [
    "Overview",
    "Shipping",
    "Customers",
    "Products",
    "Geography",
    "Data Quality",
])

# ── Date range filter (shared) ──
dates = query("SELECT MIN(Order_Date) min_dt, MAX(Order_Date) max_dt FROM orders")
min_dt = pd.Timestamp(dates["min_dt"].iloc[0])
max_dt = pd.Timestamp(dates["max_dt"].iloc[0])
date_range = st.sidebar.date_input(
    "Date range", [min_dt, max_dt], min_value=min_dt, max_value=max_dt
)
if len(date_range) == 2:
    start_dt, end_dt = date_range
else:
    start_dt, end_dt = min_dt, max_dt

# ── KPI row (used on multiple pages) ──
def kpi_row(filter_clause=""):
    where = f"WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}' {filter_clause}"
    kpi = query(f"""
        SELECT COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales), 0) AS sales,
               ROUND(AVG(od.Sales), 2) AS avg_ticket,
               COUNT(DISTINCT o.Customer_ID) AS customers
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        {where}
    """)
    return kpi.iloc[0]


# ─────────────────────────────── PAGE 1: OVERVIEW ───────────────────────────────
if page == "Overview":
    st.title("📊 Executive Overview")

    k = kpi_row()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sales", f"${k.sales:,.0f}")
    c2.metric("Orders", f"{k.orders:,}")
    c3.metric("Avg Ticket", f"${k.avg_ticket:,.2f}")
    c4.metric("Customers", f"{k.customers:,}")

    c1, c2 = st.columns(2)

    # Sales trend
    trend = query(f"""
        SELECT strftime('%Y-%m', Order_Date) AS ym, ROUND(SUM(od.Sales), 0) AS sales
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY ym ORDER BY ym
    """)
    fig = px.bar(trend, x="ym", y="sales", title="Monthly Sales", height=350)
    fig.update_layout(xaxis_tickangle=-60, margin=dict(l=20, r=20, t=40, b=40))
    c1.plotly_chart(fig, width='stretch')

    # Sales by category
    cat = query(f"""
        SELECT cat.Category_Name, ROUND(SUM(od.Sales), 0) AS sales
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY cat.Category_Name
    """)
    fig = px.pie(cat, values="sales", names="Category_Name", title="Sales by Category",
                 hole=0.4, height=350)
    c2.plotly_chart(fig, width='stretch')

    # Segment breakdown
    seg = query(f"""
        SELECT c.Segment, ROUND(SUM(od.Sales), 0) AS sales,
               COUNT(DISTINCT o.Order_ID) AS orders
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY c.Segment
    """)
    fig = px.bar(seg, x="Segment", y=["sales", "orders"], barmode="group",
                 title="Sales & Orders by Segment", height=350)
    st.plotly_chart(fig, width='stretch')


# ─────────────────────────────── PAGE 2: SHIPPING ───────────────────────────────
elif page == "Shipping":
    st.title("🚚 Shipping Efficiency")

    k = kpi_row()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Orders", f"{k.orders:,}")

    # Fulfillment by ship mode
    ship = query(f"""
        SELECT sm.Ship_Mode_Name,
               ROUND(AVG(julianday(o.Ship_Date) - julianday(o.Order_Date)), 1) AS avg_days,
               COUNT(*) AS orders,
               ROUND(SUM(od.Sales), 0) AS sales
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN ship_modes sm ON sm.Ship_Mode_ID = o.Ship_Mode_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY sm.Ship_Mode_Name
    """)
    c2.metric("Avg Fulfillment", f"{ship['avg_days'].mean():.1f} days")
    c3.metric("Avg by Mode", f"{ship['avg_days'].min():.1f} – {ship['avg_days'].max():.1f} days")

    c1, c2 = st.columns(2)
    fig = px.bar(ship, x="Ship_Mode_Name", y="avg_days",
                 title="Avg Fulfillment Days by Ship Mode",
                 color="Ship_Mode_Name", height=350)
    c1.plotly_chart(fig, width='stretch')

    # Fulfillment by region
    reg = query(f"""
        SELECT l.Region, sm.Ship_Mode_Name,
               ROUND(AVG(julianday(o.Ship_Date) - julianday(o.Order_Date)), 1) AS avg_days,
               COUNT(*) AS orders
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN ship_modes sm ON sm.Ship_Mode_ID = o.Ship_Mode_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY l.Region, sm.Ship_Mode_Name
    """)
    fig = px.bar(reg, x="Region", y="avg_days", color="Ship_Mode_Name",
                 barmode="group", title="Fulfillment Days by Region & Ship Mode",
                 height=400)
    c2.plotly_chart(fig, width='stretch')

    # Same Day violations
    sd = query(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN julianday(Ship_Date) - julianday(Order_Date) > 0 THEN 1 ELSE 0 END) AS violations
        FROM orders
        WHERE Ship_Mode_ID = (SELECT Ship_Mode_ID FROM ship_modes WHERE Ship_Mode_Name = 'Same Day')
          AND Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
    """)
    if sd["total"].iloc[0] > 0:
        pct = sd["violations"].iloc[0] / sd["total"].iloc[0] * 100
        st.warning(f"⚠️ **Same Day violations:** {sd['violations'].iloc[0]} of {sd['total'].iloc[0]} "
                   f"Same Day orders ({pct:.1f}%) shipped next day or later.")
    else:
        st.info("✅ No Same Day shipping violations in this period.")


# ─────────────────────────────── PAGE 3: CUSTOMERS ───────────────────────────────
elif page == "Customers":
    st.title("👥 Customer Analysis")

    # CLV by segment
    clv = query(f"""
        SELECT c.Segment,
               COUNT(DISTINCT c.Customer_ID) AS customers,
               ROUND(SUM(od.Sales), 0) AS total_sales,
               ROUND(SUM(od.Sales) / COUNT(DISTINCT c.Customer_ID), 2) AS avg_clv,
               ROUND(AVG(od.Sales), 2) AS avg_order_value,
               ROUND(SUM(od.Sales) * 1.0 / COUNT(DISTINCT o.Order_ID), 2) AS revenue_per_order
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN order_details od ON od.Order_ID = o.Order_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY c.Segment
    """)
    st.subheader("Customer Lifetime Value by Segment")
    c1, c2 = st.columns(2)
    fig = px.bar(clv, x="Segment", y="avg_clv", text_auto="$,.0f",
                 title="Avg CLV per Segment", height=350)
    c1.plotly_chart(fig, width='stretch')
    fig = px.bar(clv, x="Segment", y="customers", text_auto=",",
                 title="Customer Count per Segment", height=350)
    c2.plotly_chart(fig, width='stretch')

    st.dataframe(clv, width='stretch', hide_index=True)

    # Top customers
    top = query(f"""
        SELECT c.Customer_Name, c.Segment,
               COUNT(DISTINCT o.Order_ID) AS orders,
               ROUND(SUM(od.Sales), 0) AS total_spent
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        JOIN order_details od ON od.Order_ID = o.Order_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY c.Customer_ID
        ORDER BY total_spent DESC LIMIT 20
    """)
    st.subheader("🏆 Top 20 Customers by Spend")
    st.dataframe(top, width='stretch', hide_index=True)

    # Orders per customer histogram
    freq = query(f"""
        SELECT c.Customer_ID, COUNT(DISTINCT o.Order_ID) AS order_count
        FROM customers c
        JOIN orders o ON o.Customer_ID = c.Customer_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY c.Customer_ID
    """)
    fig = px.histogram(freq, x="order_count", nbins=20,
                       title="Distribution of Orders per Customer", height=350)
    st.plotly_chart(fig, width='stretch')


# ─────────────────────────────── PAGE 4: PRODUCTS ───────────────────────────────
elif page == "Products":
    st.title("📦 Product Analysis")

    # Category / sub-category drilldown
    cat = query(f"""
        SELECT cat.Category_Name, sc.Sub_Category_Name,
               ROUND(SUM(od.Sales), 0) AS sales,
               COUNT(od.Order_Detail_ID) AS units
        FROM order_details od
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        JOIN orders o ON o.Order_ID = od.Order_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY cat.Category_Name, sc.Sub_Category_Name
    """)

    c1, c2 = st.columns(2)
    fig = px.sunburst(cat, path=["Category_Name", "Sub_Category_Name"], values="sales",
                      title="Sales Hierarchy", height=400)
    c1.plotly_chart(fig, width='stretch')

    fig = px.bar(cat.sort_values("sales", ascending=False).head(15),
                 x="sales", y="Sub_Category_Name", color="Category_Name",
                 orientation="h", title="Top 15 Sub-Categories by Sales", height=400)
    c2.plotly_chart(fig, width='stretch')

    # Top products
    top_prod = query(f"""
        SELECT p.Product_Name, cat.Category_Name, sc.Sub_Category_Name,
               ROUND(SUM(od.Sales), 0) AS sales, COUNT(*) AS units
        FROM order_details od
        JOIN products p ON p.Product_ID = od.Product_ID
        JOIN sub_categories sc ON sc.Sub_Category_ID = p.Sub_Category_ID
        JOIN categories cat ON cat.Category_ID = sc.Category_ID
        JOIN orders o ON o.Order_ID = od.Order_ID
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY p.Product_ID
        ORDER BY sales DESC LIMIT 15
    """)
    st.subheader("🏆 Top 15 Products by Revenue")
    st.dataframe(top_prod, width='stretch', hide_index=True)


# ─────────────────────────────── PAGE 5: GEOGRAPHY ───────────────────────────────
elif page == "Geography":
    st.title("🌍 Geographic Analysis")

    by_state = query(f"""
        SELECT l.State, l.Region,
               ROUND(SUM(od.Sales), 0) AS sales,
               COUNT(DISTINCT o.Order_ID) AS orders,
               COUNT(DISTINCT c.Customer_ID) AS customers
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN customers c ON c.Customer_ID = o.Customer_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY l.State
    """)

    c1, c2 = st.columns(2)
    fig = px.bar(by_state.sort_values("sales", ascending=False).head(15),
                 x="sales", y="State", orientation="h",
                 title="Top 15 States by Sales", height=400, color="sales",
                 color_continuous_scale="Blues")
    c1.plotly_chart(fig, width='stretch')

    # Region breakdown
    by_region = by_state.groupby("Region").agg({"sales": "sum", "orders": "sum", "customers": "sum"}).reset_index()
    fig = px.pie(by_region, values="sales", names="Region",
                 title="Sales by Region", hole=0.4, height=350)
    c2.plotly_chart(fig, width='stretch')

    # City-level
    city = query(f"""
        SELECT l.City, l.State, ROUND(SUM(od.Sales), 0) AS sales
        FROM orders o
        JOIN order_details od ON od.Order_ID = o.Order_ID
        JOIN locations l ON l.Postal_Code = o.Postal_Code
        WHERE o.Order_Date BETWEEN '{start_dt}' AND '{end_dt}'
        GROUP BY l.City
        HAVING SUM(od.Sales) > 1000
        ORDER BY sales DESC LIMIT 20
    """)
    st.subheader("🏙️ Top Cities by Sales")
    st.dataframe(city, width='stretch', hide_index=True)


# ─────────────────────────────── PAGE 6: DATA QUALITY ───────────────────────────────
elif page == "Data Quality":
    st.title("🔍 Data Quality Issues Found")

    st.markdown("""
    The flat-file approach lets data entry errors through. Below are the issues discovered
    during EDA — all fixable with an input layer and a normalized schema.
    """)

    issues = pd.read_csv("data_quality_examples.csv")

    for issue_name in issues["Issue"].unique():
        subset = issues[issues["Issue"] == issue_name].head(3)
        with st.expander(f"**{issue_name}** — {len(issues[issues['Issue'] == issue_name])} occurrences"):
            for _, r in subset.iterrows():
                st.code(f"Row {r['RowID']}: {r['Value']}")
                st.caption(f"Should be: {r['ShouldBe']} | Context: {r['Context']}")
            st.caption(f"… and {len(subset) - 3} more" if len(subset) > 3 else "")

    # Product ID collision table
    st.subheader("Product ID Collisions (32 IDs)")
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

    # ZIP issues
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
                st.code(f"Stored: {pc:04d} → Should be: {pc:05d} | {r['City']}, {r['State']} ({r['orders']} orders)")
