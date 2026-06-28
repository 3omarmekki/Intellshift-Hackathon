# What We Found in the Data

## The Big Picture

We looked at 9,800 sales records (2015-2018) and found clear evidence of the problems described in the business statement. The data is a flat-file dump of orders from a US office-supply company. Here's what matters.

## The Duplication Problem (Data Normalization)

- **793 unique customers** spread across **9,800 rows** — the same customer's name, location, and segment is repeated on every single purchase line. That's 12x unnecessary duplication.
- **1,861 unique products** repeated 5x on average.
- We found **55 cities** that appear in multiple states (e.g., "Apple Valley" exists in both Minnesota and California). In a normalized database, each city would be stored once with a correct state FK — here, typos or ambiguities slip in.
- Every customer, product, and location edit requires updating thousands of rows. Miss one, and reports become inconsistent.

## Shipping & Operations

| Ship Mode | Avg Days to Deliver |
|-----------|-------------------|
| Same Day  | 0                 |
| First Class | ~2 days         |
| Second Class | ~3 days         |
| Standard Class | ~5 days      |

- **Standard Class** is the most used mode, and it's also the slowest (up to 7 days). The company has a blind spot on which regions or products cause the worst delays.
- All regions perform roughly the same on average, but there's no real-time dashboard — teams rely on manual Excel reports to spot a problem.

## Customer Value

- **Average customer spend: $2,852** (median: $2,215) — a few big buyers pull the average up.
- Corporate customers have the highest average CLV ($2,917), but Consumer segment has the most customers (409 vs 236 corporate).
- Top customer (Sean Miller, Home Office) spent $25,043 across 5 orders.
- The data has **no recency/frequency scoring or segment-level CLV tracking** — the company currently can't identify who their best customers are without manually pivoting spreadsheets.

## Sales Distribution

- Sales are heavily right-skewed: most orders are small (< $55 median), but some orders hit $22,638.
- **Category breakdown:** ~36% Technology, ~32% Furniture, ~32% Office Supplies.
- Top sub-categories by revenue: Phones, Chairs, Storage, Tables, Binders.

## Geographic Spread

- California leads by a wide margin, followed by New York and Texas.
- The West region generates the most revenue, then East, Central, South.

## How to Use This at the Hackathon

1. **Prove the problem exists** — The 12x customer duplication ratio, 55 ambiguous city names, and zero automated reporting are all concrete evidence that the current system is broken. Show the numbers.

2. **Your solution should center on normalization** — Split into Customers, Products, Locations, and Orders tables. Every business pain traces back to the flat-file approach.

3. **Build the dashboards they're missing** — The ask in the problem statement is clear: real-time shipping efficiency, CLV tracking, and market segmentation. A normalized DB + a BI layer (or simple API + dashboard) directly addresses the business impact.

4. **The data quality findings make the pitch stronger** — 11 missing postal codes across 9,800 rows is a small number, but it's proof that manual data entry without constraints leads to dirty data. A proper schema with foreign keys and constraints eliminates this entirely.
