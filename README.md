# O JAMP — Superstore Enterprise Intelligence

Interactive BI dashboard with 3 AI models and a Symbolic AI rule engine for the IntelliShift Data Intelligence Hackathon.

**Live dashboard:** https://intellshift-hackathon-cpf4xwbr5jfqjufuhs8gxr.streamlit.app/

## Quick Start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard.py
```

## Documentation

- **`BUSINESS.md`** — Business overview: problem, solution, dashboard walkthrough, AI insights
- **`TECHNICAL.md`** — Technical deep-dive: architecture, database schema, 3 AI models, Symbolic AI, deployment

## What's Included

- Normalized SQLite database (8 tables) replacing a flat CSV
- 9-page Streamlit dashboard with real-time filters
- K-Means customer clustering (4 AI profiles)
- Sales forecasting (Random Forest)
- Shipping efficiency prediction (Random Forest)
- 816 Symbolic AI marketing rules (15 mining strategies)
- Supply chain mock data (5 warehouses, 3 carriers, 3,879 inventory records)
