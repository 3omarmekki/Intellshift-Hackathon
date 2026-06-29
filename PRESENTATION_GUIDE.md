# Superstore Enterprise Intelligence

## Hackathon Presentation Guide

---

# 📋 Problem Statement

## Business Context

A growing retail company relies entirely on **fragmented flat files and Excel spreadsheets** to manage sales, customers, inventory, and operations.

## Core Issues

| Issue | Impact |
|-------|--------|
| **Data duplication** — customer, product, and location info repeated in every row | Integrity risks, update nightmares |
| **No normalization** — single flat table for everything | Performance degradation as data grows |
| **Manual ETL** — teams manually prepare reports from multiple files | Error-prone, reactive, slow |
| **No real-time BI** — executives get static weekly sheets | Delayed response to market shifts |
| **Shipping blind spots** — no delay tracking across modes & regions | Poor fulfillment, unhappy customers |
| **No CLV tracking** — can't segment customers or measure lifetime value | Can't run targeted marketing |
| **No AI/automation** — decisions based on gut, not data | Missed revenue opportunities |

## Strategic Goal

> Transition from manual flat-file management to a **centralized relational database** with **automated pipelines**, **Business Intelligence**, **AI-powered customer analytics**, and **Symbolic AI recommendations**.

---

# 🏗 Solution Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Data.csv  │ ──▶ │  ETL Pipeline│ ──▶ │  superstore.db  │
│ (flat file) │     │(normalize +  │     │  (normalized)   │
└─────────────┘     │  load)       │     └────────┬────────┘
                    └──────────────┘              │
                         │                        │
                         ▼                        ▼
                 ┌──────────────┐     ┌──────────────────┐
                 │ Mock Ops     │     │ Customer Seg.    │
                 │ (warehouses, │     │ (K-Means → CSV)  │
                 │  carriers,   │     └────────┬─────────┘
                 │  inventory)  │              │
                 └──────┬───────┘              │
                        │                      │
                        ▼                      ▼
                 ┌──────────────────────────────────┐
                 │       Streamlit Dashboard        │
                 │  (Enterprise Intelligence UI)     │
                 │  ┌────────────────────────────┐   │
                 │  │ 9 Pages · Live Filters     │   │
                 │  │ AI Clustering · AI Rules   │   │
                 │  │ US Map · Supply Chain      │   │
                 │  │ Add Customer · CLV         │   │
                 │  └────────────────────────────┘   │
                 └──────────────────────────────────┘
```

---

# 🗄 Database Design

## Normalized Schema (8 tables)

```
customers         (Customer_ID, Name, Segment)
locations         (Postal_Code, City, State, Country, Region)
categories        (Category_ID, Name)
sub_categories    (Sub_Category_ID, Category_ID, Name)
products          (Product_ID, Sub_Category_ID, Name)
orders            (Order_ID, Date, Ship_Date, Ship_Mode, Customer_ID, Postal_Code)
order_details     (Detail_ID, Order_ID, Product_ID, Sales)
ship_modes        (Ship_Mode_ID, Name)
```

## Mock Operational Tables

```
warehouses   (ID, Name, City, State, Region, Capacity, Load, Staff, Queue)
carriers     (ID, Name, Active_Trucks, Avg_Delay_Days)
inventory    (ID, Product_ID, Warehouse_ID, Stock, Reserved, Incoming)
```

## Key Stats

| Table | Records |
|-------|---------|
| Customers | 794 |
| Orders | 4,916 |
| Order Details | 9,789 |
| Products | 1,892 |
| Locations | 48 states |
| Warehouses | 5 |
| Carriers | 3 |
| Inventory records | 3,879 |

---

# 🤖 AI Component 1: K-Means Customer Clustering

## Algorithm

| Detail | Value |
|--------|-------|
| **Model** | K-Means (unsupervised) |
| **Clusters** | 4 |
| **Features** | Total Spend, Order Count, Avg Order Value, Purchase Frequency |
| **Scaling** | StandardScaler |
| **Random State** | 42 |
| **Silhouette Score** | **0.3447** (meaningful separation) |

## The 4 Customer Profiles

| Profile | Customers | Behavior |
|---------|-----------|----------|
| 🟥 **VIP Customers** | 179 (23%) | High spenders, frequent buyers, highest CLV |
| 🟦 **Regular Customers** | 259 (33%) | Steady purchasers, consistent patterns |
| 🟩 **Medium Value Customers** | 310 (39%) | Moderate spenders, room to upsell |
| 🟨 **Occasional Customers** | 46 (6%) | Infrequent, low-value, need reactivation |

## Business Recommendations per Profile

| Profile | Strategy |
|---------|----------|
| **VIP** | Exclusive loyalty program, early access, dedicated support |
| **Regular** | Points-based rewards, personalized recommendations |
| **Medium Value** | Upsell campaigns, bundle deals, volume discounts |
| **Occasional** | Re-engagement emails, limited-time discounts, best-seller highlights |

---

# 🧠 AI Component 2: Symbolic AI Rule Engine

## What is Symbolic AI?

Unlike neural networks (black boxes), **Symbolic AI** mines explicit, human-readable rules from data. Every rule has a clear **IF → THEN** structure with measurable **Lift** and **Support**.

**Why Symbolic AI for retail?**
- ✅ **Interpretable** — executives can read and trust the rules
- ✅ **Sparse-data friendly** — works with small/medium datasets
- ✅ **Actionable** — each rule is a ready-to-use business insight
- ✅ **No hallucination** — rules are grounded in real data

## Results: 816 Mined Rules

| Rule Type | Count | Business Use |
|-----------|-------|--------------|
| Subcategory → Top Product | 333 | "Accessories → best-selling keyboard" |
| Segment + Region → Subcategory | 99 | "Corporate in West → buy Chairs" |
| Combo Product (cross-sell) | 81 | "If Product A, also buy Product B" |
| Seasonal Patterns | 70 | "Product X peaks in December" |
| Customer Similarity | 52 | "Look-alike targeting" |
| Region → Subcategory | 41 | "West region → Technology products" |
| Segment → Subcategory | 33 | "Consumers → Furniture" |
| CLV → Subcategory | 31 | "High-value customers → Accessories" |
| Recency → Subcategory | 27 | "Recently bought X → likely to buy Y" |
| Category → Subcategory | 17 | "Technology → Phones" |
| Price Tier → Subcategory | 16 | "Premium buyers → high-end Furniture" |
| Subcategory Complementary | 12 | "Buying Chair → also buy Table" |
| Cross-recommendations | 2 | Cross-product suggestions |
| Segment → Price Tier | 2 | "Corporate → mid-range pricing" |

**Total: 816 validated rules**

## Example Rules

| Rule | Lift | Action |
|------|------|--------|
| If "Corporate" + "West" → Buy "Chairs" | 3.2× | Targeted B2B campaign |
| If "Chairs" → Also buy "Tables" | 2.1× | Bundle offer |
| If "Accessories" → "Logitech Keyboard" | 1.8× | Feature best-seller |
| If "December" → "Holiday decorations" | 4.5× | Seasonal promotion |

---

# 🖥 Dashboard: 9 Pages

## 1. Executive Overview
- **KPIs**: Revenue, Transactions, Avg CLV, Active Customers
- Monthly revenue trend bar chart
- Revenue by category (pie)
- Revenue & transactions by customer type
- **CLV section**: Avg CLV by customer type + Avg CLV by AI profile

## 2. US Map
- Choropleth of revenue/transactions/customers by state
- Top 5 state metrics sidebar
- City breakdown
- Product coverage heatmap by sub-category

## 3. Supply Chain
- Warehouse load vs capacity
- Staff vs queue per warehouse
- Carrier delay & fleet status
- Inventory levels by warehouse
- Shipping delay diagnosis (scatter: load vs delay)
- Warehouse routing recommendations

## 4. Clustered AI
- K-Means model quality (silhouette score)
- 4 customer profiles with descriptions
- Profile distribution pie chart
- Profile characteristics table (Avg CLV, Orders, AOV, Frequency)
- PCA visualization
- Business recommendations per profile
- All customers with AI profile assignments

## 5. Marketing Campaigns
- **5 campaign types**: Cross-sell, Upsell, Seasonal, Regional, VIP Retention
- Uses real Symbolic AI rules (816 total)
- Each rule shown as card: Antecedent → Consequent, Lift, Support, Action label
- Filterable by campaign type

## 6. Per-Product Segments
- Pick Category → Product Line → Product
- Shows which AI customer profiles buy that product
- Pie chart + segment breakdown bar chart

## 7. Symbolic AI Rules
- Browse all 816 rules
- Filters: Rule type, Min Lift, Min Support
- Rule type distribution bar chart

## 8. Add Customer (Judge Tool)
- Form to insert new customers
- Optional: add order + order detail
- Triggers full AI pipeline recompute
- Cache clear + auto-refresh

## 9. Data Integrity
- Data quality issues from flat-file era
- Product ID collisions (32 IDs, multiple names)
- ZIP codes with missing leading zeros

## Filter System

Filters appear as a horizontal bar at the top of every page:

| Filter | Options |
|--------|---------|
| 📅 Period | Date range picker |
| 🏷️ Customer type | Consumer, Corporate, Home Office |
| 🌎 Region | East, Central, West, South |
| 📦 Category | Furniture, Office Supplies, Technology |
| 👤 Customer | Dropdown of all 794 customers |

Filters persist across page navigation and affect ALL charts/tables.

## Built-in Dashboard Guide

The sidebar contains a **📖 Dashboard Guide** expander with:
- System overview
- Navigation help
- Filter usage instructions
- Page-by-page descriptions
- Pro tips
- Technical details

---

# 📊 Key Results

## Before vs After

| Capability | Before (Flat File) | After (Our System) |
|------------|-------------------|-------------------|
| **Data storage** | 1 CSV, 18 columns, 9,800 rows | 8 normalized tables |
| **Data quality** | 11 missing ZIPs, 32 duplicate product IDs | Schema-enforced integrity |
| **Reporting** | Manual Excel sheets | Real-time BI dashboard |
| **Customer insights** | Raw names only | 4 AI-powered profiles |
| **Marketing intelligence** | None | 816 actionable rules |
| **Supply chain visibility** | None | 5 warehouses, 3 carriers, real-time inventory |
| **CLV tracking** | Impossible | Per-customer & per-segment |
| **Judge demo capability** | N/A | Add customer → auto recompute |

## Data Quality Issues Found

| Issue | Count |
|-------|-------|
| Null postal codes | 11 records |
| Product ID collisions (1 ID → multiple names) | 32 IDs |
| ZIP codes missing leading zero | 10+ locations |
| Customer name inconsistencies | "Sean Miller" vs "Sean A. Miller" |
| City/state mismatches | Multiple |

---

# 🚀 How to Run

```bash
# 1. Set up environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run the full pipeline (mock data + clustering)
python run_pipeline.py

# 3. Launch the dashboard
streamlit run dashboard.py
```

---

# 📁 File Structure

```
├── dashboard.py                 # Main Streamlit app (9 pages)
├── customer_segmentation.py     # K-Means pipeline (features → clustering)
├── mock_operations.py           # Warehouse, carrier, inventory tables
├── run_pipeline.py              # Orchestrator (mock data + clustering)
├── minedrules.csv               # 816 Symbolic AI rules
├── superstore.db                # Normalized database
├── customer_clusters.csv        # Pre-computed K-Means assignments
├── cluster_metrics.json         # Silhouette score
├── cluster_centers.csv          # Cluster center profiles
├── mining.py / rules.py         # Rule mining engine
├── mine_all.py                  # 15-strategy rule miner
├── knowledge_base.py            # Knowledge base for Symbolic AI
├── kb_explorer.py               # KB explorer (port 8509)
├── preprocess_and_load.py       # ETL: CSV → normalized DB
└── data_quality_examples.csv    # Documented data quality issues
```

---

# 👥 Team Notes for Presentation

## Suggested flow (10 min)

1. **Problem** (1 min) — Flat files, data duplication, no BI
2. **Database solution** (1 min) — Normalized schema, ETL pipeline
3. **Dashboard walkthrough** (3 min) — Executive Overview → US Map → Supply Chain
4. **AI — Clustering** (2 min) — K-Means, 4 profiles, silhouette score, business recs
5. **AI — Symbolic Rules** (2 min) — 816 rules, no black box, ready-to-use campaigns
6. **Judge demo** (1 min) — Add customer form → auto pipeline recompute

## Key talking points

- "816 symbolic rules vs neural network — every rule is human-readable and actionable"
- "K-Means identifies 4 distinct customer types — from VIP ($X avg CLV) to Occasional ($Y)"
- "The dashboard is **time-variant** — new data in, new clusters out, dashboard updates live"
- "Mock operational tables show how real supply chain data enables delay diagnosis"
