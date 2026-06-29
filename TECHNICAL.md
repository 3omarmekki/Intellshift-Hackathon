# O JAMP — Technical Documentation: Superstore Enterprise Intelligence

## Architecture

```
Data.csv (flat file)
    │
    ▼
preprocess_and_load.py ───► superstore.db (SQLite, 8 normalized tables)
    │
    ├── run_pipeline.py
    │     ├── mock_operations.py ──► warehouses, carriers, inventory tables
    │     └── customer_segmentation.py ──► customer_clusters.csv, kmeans_model.pkl
    │
    ├── mine_all.py (15 Symbolic AI strategies) ──► minedrules.csv (816 rules)
    │
    └── dashboard.py (Streamlit, 9 pages)
```

## Database Schema

### Core Tables (normalized from Data.csv)

| Table | Rows | Primary Key | Notes |
|-------|------|-------------|-------|
| `customers` | 794 | Customer_ID | Segment: Consumer, Corporate, Home Office |
| `locations` | 627 | Postal_Code, City, State | 48 states, 4 regions (East, Central, South, West) |
| `categories` | 3 | Category_ID | Furniture, Office Supplies, Technology |
| `sub_categories` | 17 | Sub_Category_ID | FK → categories |
| `products` | 1,892 | Product_ID (TEXT) | FK → sub_categories |
| `orders` | 4,916 | Order_ID | FK → customers, locations, ship_modes |
| `order_details` | 9,789 | Order_Detail_ID | FK → orders, products |
| `ship_modes` | 4 | Ship_Mode_ID | Standard Class, Second Class, First Class, Same Day |

### Mock Operational Tables (for Supply Chain demo)

| Table | Rows | Purpose |
|-------|------|---------|
| `warehouses` | 5 | Capacity, load, staff, queue per region |
| `carriers` | 3 | Fleet size, avg delay per carrier |
| `inventory` | 3,879 | Stock/reserved/incoming per product per warehouse |

## ETL Pipeline

`preprocess_and_load.py` handles:
1. Read `Data.csv` (9,800 rows)
2. Split into 8 normalized tables
3. Create foreign key relationships
4. Load into `superstore.db`

Data quality fixes applied:
- 11 null postal codes flagged
- 32 product ID collisions documented
- Leading-zero ZIP codes preserved as REAL (with data quality notes in dashboard)

## AI Model 1: K-Means Customer Segmentation

**File:** `customer_segmentation.py`

| Detail | Value |
|--------|-------|
| Algorithm | K-Means (scikit-learn) |
| Clusters | 4 |
| Features | Customer_Total_Sales, Customer_Order_Count, Average_Order_Value, Purchase_Frequency |
| Scaling | StandardScaler |
| Random State | 42 |
| Silhouette Score | 0.3447 |
| Exports | `customer_clusters.csv` (with PCA coordinates), `cluster_metrics.json`, `cluster_centers.csv`, `kmeans_model.pkl`, `scaler.pkl` |

**4 Cluster Centers (inverted from scaled):**

| Cluster | Avg Sales | Avg Orders | Avg Order Value |
|---------|-----------|------------|-----------------|
| VIP (179) | Highest | Highest | High |
| Regular (259) | Medium-High | Medium | Medium |
| Medium Value (310) | Medium | Medium-Low | Medium |
| Occasional (46) | Low | Low | Low |

## AI Model 2: Sales Forecasting

**Location:** `Hackathon.ipynb` (Cell 58)

| Detail | Value |
|--------|-------|
| Algorithm | Random Forest Regressor (scikit-learn) |
| Target Variable | Sales (dollar value per order detail) |
| Features | Customer total sales, customer order count, customer lifetime, product total sales, product order count, quarter, shipping speed indicators, and other engineered features |
| Encoding | One-hot encoding for categorical variables (Quarter, Shipping_Speed) |
| Scaling | StandardScaler for numerical features |
| Train/Test Split | Standard 80/20 |
| Evaluation Metrics | R², MAE, RMSE |
| Outputs | Actual vs predicted scatter plot, feature importance bar chart, residual plot |

The model enables revenue planning, anomaly detection in order values, and inventory pre-stocking for predicted high-value orders.

## AI Model 3: Shipping Efficiency Prediction

**Location:** `Hackathon.ipynb` (Cell 60)

| Detail | Value |
|--------|-------|
| Algorithm | Random Forest Regressor (scikit-learn) |
| Target Variable | Shipping Delay (Ship_Date - Order_Date, in days) |
| Features | Customer total sales, customer order count, customer lifetime, product order count (aggregated to order level), quarter, shipping mode indicators |
| Encoding | One-hot encoding for categorical variables (Quarter) |
| Scaling | StandardScaler for numerical features |
| Train/Test Split | Standard 80/20 |
| Evaluation Metrics | R², MAE, RMSE |
| Outputs | Actual vs predicted scatter plot, feature importance bar chart, residual plot |

Enables proactive carrier switching, customer communication before delays, and SLA compliance monitoring.

## Symbolic AI Rule Engine

### Architecture

```
knowledge_base.py ──► NetworkX knowledge graph (1,626 nodes, 2,251 edges)
mining.py          ──► Apriori algorithm implementation
mine_all.py        ──► 15 mining strategies ──► minedrules.csv (816 rules)
rules.py           ──► Rule DSL + InferenceEngine + Noisy-OR scoring
```

### 15 Mining Strategies

| # | Strategy | Rules | Example |
|---|----------|-------|---------|
| 1 | SubCategory → Top Product | 333 | Accessories → Logitech G19 Keyboard |
| 2 | Customer Segment → SubCategory | 33 | Consumer → Accessories |
| 3 | Region → SubCategory | 41 | Central → Appliances |
| 4 | CLV Tier → SubCategory | 31 | Gold → Copiers |
| 5 | Price Tier → SubCategory | 16 | Budget → Binders |
| 6 | Segment + Region → SubCategory | 99 | Corporate + Central → Copiers |
| 7 | Customer Similarity (Product → Product) | 52 | Headset → Labels (58.7× lift) |
| 8 | SubCategory Complementarity | 12 | Copiers → Appliances |
| 9 | Category → SubCategory | 17 | Technology → Accessories |
| 10 | Seasonal (Month → SubCategory) | 70 | August → Supplies |
| 11 | Recency Tier → SubCategory | 27 | Active → Accessories |
| 12 | Combo Product (Segment+Region+CLV → Product) | 81 | Home Office + South + Gold → Binding Combs |
| 13 | SubCat Cross-Recommend | 2 | Binders → Copiers |
| 14 | Segment → Price Tier | 2 | Corporate → Premium |
| 15 | Product Co-occurrence | — | Complementary products |

### Rule Scoring

Each rule includes:
- **Support:** fraction of orders matching the antecedent
- **Confidence:** P(consequent | antecedent)
- **Lift:** P(consequent | antecedent) / P(consequent) — how much more likely than random

### Rule DSL (rules.py)

```python
Rule(
    name="Corporate_Central_Copiers",
    conditions=[Condition("segment", "eq", "Corporate"), Condition("region", "eq", "Central")],
    actions=[Action("recommend", "SubCategory:Copiers")],
    strength=0.0232, lift=1.73
)
```

## Dashboard Pages

| Page | Key Content |
|------|-------------|
| Executive Overview | KPIs, revenue trend, category breakdown, CLV by segment and AI profile |
| US Map | State-level choropleth, top 5 states, city breakdown |
| Supply Chain | Warehouse load, carrier delays, inventory, routing recommendations |
| Clustered AI | 4 profiles, PCA visualization, business recommendations, customer table |
| Marketing Campaigns | 816 rules grouped by 5 campaign types with action labels |
| Per-Product Segments | Category → SubCategory → Product; shows which AI segment buys what |
| Symbolic AI Rules | All 816 rules with full filtering by type, lift, support |
| Add Customer | Insert form + auto pipeline recompute |
| Data Integrity | Data quality issues from flat-file era |

## Deployment

- **Platform:** Streamlit Community Cloud
- **Entry point:** `dashboard.py`
- **Dependencies:** streamlit, pandas, plotly, scikit-learn, numpy (see `requirements.txt`)
- **Config:** `.streamlit/config.toml`
- **Live URL:** [https://intellshift-hackathon-cpf4xwbr5jfqjufuhs8gxr.streamlit.app/](https://intellshift-hackathon-cpf4xwbr5jfqjufuhs8gxr.streamlit.app/)

## File Inventory

```
├── dashboard.py                  # Streamlit app (9 pages, 1,004 lines)
├── customer_segmentation.py      # K-Means pipeline
├── mock_operations.py            # Warehouse/carrier/inventory seeder
├── run_pipeline.py               # Pipeline orchestrator
├── preprocess_and_load.py        # CSV → normalized DB
├── mining.py                     # Apriori algorithm
├── rules.py                      # Symbolic AI rule engine
├── mine_all.py                   # 15-strategy rule miner
├── knowledge_base.py             # Knowledge graph builder
├── kb_explorer.py                # Interactive KB explorer (port 8509)
├── Hackathon.ipynb               # Full notebook (EDA + 3 AI models + DB creation)
├── requirements.txt              # Python dependencies
├── superstore.db                 # SQLite database
├── minedrules.csv                # 816 Symbolic AI rules
├── customer_clusters.csv         # K-Means assignments with PCA
├── cluster_metrics.json          # Silhouette score (0.3447)
├── cluster_centers.csv           # Cluster profiles
├── .streamlit/config.toml        # Streamlit Cloud config
└── data_quality_examples.csv     # Documented data issues
```
