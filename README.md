# Intellishift Hackathon — Superstore BI Dashboard

Interactive BI dashboard built with Streamlit + SQLite for the Superstore sales dataset.

## What It Shows

### 📊 Executive Overview
- Monthly sales bar chart
- Sales breakdown by product category (pie chart)
- Sales & orders by customer segment
- KPI cards: total sales, order count, avg ticket, customer count

### 🚚 Shipping Efficiency
- Avg fulfillment days by ship mode
- Fulfillment days by region & ship mode
- Same Day shipping violation detection (orders shipped later than same day)

### 👥 Customer Analysis
- CLV (Customer Lifetime Value) by segment
- Customer count per segment
- Top 20 customers by total spend
- Distribution of orders per customer

### 📦 Product Analysis
- Sales hierarchy sunburst (category → sub-category)
- Top 15 sub-categories by sales
- Top 15 products by revenue

### 🌍 Geographic Analysis
- Top 15 states by sales
- Sales by region (pie chart)
- Top 20 cities by sales

### 🔍 Data Quality
- Catalog of data quality issues found during EDA (ZIP truncation, special chars, Product ID collisions, etc.)
- Live queries showing affected records from the database

## How to Run

### 1. Clone & enter
```bash
git clone <repo-url>
cd Intellishift-Hackathon
```

### 2. Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# or venv\Scripts\activate  # Windows
```

### 3. Install dependencies
```bash
pip install streamlit pandas plotly
```

### 4. Run the dashboard
```bash
streamlit run dashboard.py
```

Open http://localhost:8501 in your browser.

### 5. (Optional) Rebuild the database
```bash
python preprocess_and_load.py
```

## Project Structure
```
├── dashboard.py              ← Streamlit BI dashboard (6 pages)
├── preprocess_and_load.py    ← Builds superstore.db from Data.csv
├── superstore.db             ← SQLite database (8 normalized tables)
├── Data.csv                  ← Raw Superstore data (9,800 rows)
├── preprocessingANDtables.ipynb  ← Original ETL notebook (schema source)
├── eda.ipynb / eda_executed.ipynb ← Exploratory Data Analysis
├── DATA_QUALITY_FINDINGS.md  ← Data quality issues catalog
├── data_quality_examples.csv ← 61 example rows for 10 issue types
└── Business Problem Statement.txt  ← Hackathon problem brief
```

## Database Schema (8 tables)
| Table | Rows | Description |
|-------|------|-------------|
| customers | 793 | Customer_ID, Name, Segment |
| locations | 627 | Postal_Code, City, State, Region |
| ship_modes | 4 | Ship_Mode_ID, Name |
| categories | 3 | Category_ID, Name |
| sub_categories | 17 | Sub_Category_ID, Name, Category_ID |
| products | 1,892 | Product_ID, Sub_Category_ID, Product_Name |
| orders | 4,916 | Order_ID, Customer_ID, Ship_Mode_ID, Postal_Code, Order_Date, Ship_Date |
| order_details | 9,789 | Order_Detail_ID, Order_ID, Product_ID, Sales, Quantity, Discount, Profit |

All tables indexed on foreign keys and lookup columns.
