# O JAMP — Business Overview: Superstore Enterprise Intelligence

## The Problem

A growing US office-supply company manages all operations through a single flat CSV file (9,800 rows, 18 columns). Customer details, product info, and location data are duplicated on every transaction row. This causes:

- **Slow reporting** — no real-time dashboards, only static Excel sheets
- **Data corruption** — 11 missing ZIP codes, 32 product IDs mapped to multiple names, leading zeros stripped from 429 ZIP codes
- **No customer insights** — impossible to track Customer Lifetime Value (CLV) or segment buyers
- **Supply chain blind spots** — no way to monitor shipping delays, warehouse loads, or inventory levels
- **No AI-driven marketing** — all decisions based on intuition, not data

## Our Solution

We replaced the flat file with a **centralized SQLite database** (8 normalized tables) and built an **interactive Streamlit dashboard** with **3 AI models** and a **Symbolic AI rule engine** — all working together to deliver real-time business intelligence.

### What Executives Get

| Feature | What It Shows |
|---------|---------------|
| **Executive Overview** | Revenue ($2.3M), transactions (4,916), CLV by segment, monthly trends |
| **US Map** | Revenue/transactions by state, top 5 states, city breakdown |
| **Supply Chain** | Warehouse load vs capacity, carrier delays, inventory levels, shipping delay diagnosis |
| **Marketing Campaigns** | 816 ready-to-use Symbolic AI rules for cross-sell, upsell, seasonal, regional, and VIP campaigns |
| **Customer Profiles** | 4 AI-identified segments (VIP, Regular, Medium Value, Occasional) with business recommendations |
| **Per-Product Analysis** | Which AI customer segments buy which products |

## The 3 AI Models

### 1. K-Means Customer Clustering
Groups 794 customers into 4 actionable profiles:

| Profile | Customers | Behavior | Strategy |
|---------|-----------|----------|----------|
| 🟥 VIP | 179 (23%) | High spenders, frequent, highest CLV | Exclusive loyalty program |
| 🟦 Regular | 259 (33%) | Steady, consistent patterns | Points-based rewards |
| 🟩 Medium Value | 310 (39%) | Moderate spenders, room to upsell | Bundle deals, volume discounts |
| 🟨 Occasional | 46 (6%) | Infrequent, low-value | Re-engagement emails, best-seller highlights |

**Business impact:** Marketing can now target each group with tailored campaigns instead of blasting everyone.

### 2. Sales Forecasting (Random Forest)
Predicts the dollar value of each order. Enables:
- Revenue planning and quarterly projections
- Inventory pre-stocking for predicted high-value orders
- Anomaly detection (actual vs predicted)

### 3. Shipping Efficiency Prediction (Random Forest)
Predicts shipping delay in days for every order. Enables:
- Proactive carrier switching when delays are predicted
- Customer communication before delays occur
- SLA compliance monitoring

## Symbolic AI: 816 Ready-to-Use Marketing Rules

Unlike neural network black boxes, our Symbolic AI engine mines explicit **IF → THEN** rules from transaction data. Every rule has a measurable **lift** (how much more likely) and is immediately actionable.

**4 example rules → 4 campaigns:**

| If... | Then... | Campaign |
|-------|---------|----------|
| Customer bought Logitech G35 Headset | Recommend Avery 486 (58.7× more likely) | Cross-sell: office supplies after electronics |
| Month is August | Supplies sales spike (1.95× average) | Seasonal: back-to-school blast |
| Corporate segment in Central region | Buy Copiers (1.73× more likely) | Regional B2B outbound sales |
| Home Office + South + Gold CLV | Buy Binding Combs (32.4× more likely) | Micro-segment email automation |

## Supply Chain Mock Data

We built realistic mock tables to demonstrate operational visibility:

| Asset | Count | What It Shows |
|-------|-------|---------------|
| Warehouses | 5 (one per US region + central) | Load %, staff, queue length, routing recommendations |
| Carriers | 3 (FastEx, ParcelPro, MailConnect) | Avg delay days, fleet size |
| Inventory | 3,879 records | Stock vs reserved vs incoming per product per warehouse |

## Dashboard Deployed

Live URL: [https://intellshift-hackathon-cpf4xwbr5jfqjufuhs8gxr.streamlit.app/](https://intellshift-hackathon-cpf4xwbr5jfqjufuhs8gxr.streamlit.app/)

---

*Built for the IntelliShift Data Intelligence Hackathon. See TECHNICAL.md for architecture, schema, and model details.*
