import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from pyvis.network import Network
from knowledge_base import KnowledgeBase
from rule_engine import InferenceEngine, build_customer_facts, RULES
import tempfile
import os

st.set_page_config(page_title="Knowledge Base Explorer", layout="wide")

# ── Load knowledge base (cached) ──
@st.cache_resource
def load_kb():
    return KnowledgeBase()

@st.cache_resource
def load_engine():
    return InferenceEngine()

kb = load_kb()
engine = load_engine()

# ── Color palette for entity types ──
COLORS = {
    "Category": "#FF6B6B",
    "SubCategory": "#FFA94D",
    "Product": "#69DB7C",
    "Customer": "#74C0FC",
    "Segment": "#DA77F2",
    "Location": "#FFD43B",
    "Region": "#FF922B",
    "ShipMode": "#20C997",
    "PriceTier": "#F06595",
}
DEFAULT_COLOR = "#ADB5BD"

# ── Sidebar navigation ──
st.sidebar.title("🔮 KB Explorer")
st.sidebar.markdown("Explore the Superstore **knowledge base** — entities, relations, symbols, and rules.")
page = st.sidebar.radio("Navigate", [
    "🗺️ Knowledge Graph",
    "🔍 Entity Browser",
    "⚙️ Rule Engine",
    "📖 Symbol Dictionary",
])

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Graph stats:** {kb.G.number_of_nodes():,} nodes · {kb.G.number_of_edges():,} edges")


# ═══════════════════════════════════════════════════════════════════
# PAGE 1: KNOWLEDGE GRAPH
# ═══════════════════════════════════════════════════════════════════
if "Knowledge Graph" in page:
    st.title("🗺️ Knowledge Graph Explorer")
    st.markdown("Interactive graph of the Superstore ontology. Drag nodes, zoom, and click to inspect.")

    with st.expander("🎛️ Filters", expanded=True):
        c1, c2, c3 = st.columns(3)
        types = kb.get_entity_types()
        selected_types = c1.multiselect("Entity types to show", sorted(types),
                                        default=["Category", "SubCategory", "Segment", "Region", "PriceTier"],
                                        key="kg_types")
        max_nodes = c2.slider("Max nodes", 10, 200, 60, key="kg_max")
        show_edges = c3.checkbox("Show edge labels", True, key="kg_edges")

        search_q = st.text_input("🔎 Focus on entity (name or ID)", placeholder="e.g. Furniture, Sean Miller, FUR-BO-10002213")

    # Build the subgraph
    sub_nodes = []
    target_id = None

    if search_q:
        results = kb.search_entities(search_q, limit=10)
        if results:
            target_id = results[0][0]
            # Add target + its neighbors
            sub_nodes.append(target_id)
            for nid, _, _ in kb.get_neighbors(target_id, max_nodes=50):
                if nid not in sub_nodes:
                    sub_nodes.append(nid)
            # Also add neighbors of neighbors for context
            more = []
            for nid in list(sub_nodes):
                for nnid, _, _ in kb.get_neighbors(nid, max_nodes=10):
                    if nnid not in sub_nodes and nnid not in more:
                        more.append(nnid)
            sub_nodes.extend(more[:30])
        else:
            st.warning("No matching entities found.")

    if not sub_nodes:
        # Filter by type
        for nid, attrs in kb.G.nodes(data=True):
            if attrs.get("type") in selected_types:
                sub_nodes.append(nid)
            if len(sub_nodes) >= max_nodes:
                break

    # Build pyvis network
    net = Network(height="650px", width="100%", directed=True, notebook=False)
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=200, spring_strength=0.01)

    added = set()
    for nid in sub_nodes:
        if nid not in added and nid in kb.G:
            attrs = kb.G.nodes[nid]
            etype = attrs.get("type", "Unknown")
            label = attrs.get("name", nid.split(":", 1)[-1] if ":" in nid else nid)
            color = COLORS.get(etype, DEFAULT_COLOR)
            title = f"<b>{label}</b><br/>Type: {etype}<br/>ID: {nid}"
            for k, v in attrs.items():
                if k not in ("type", "name") and not isinstance(v, (set, list, dict)):
                    title += f"<br/>{k}: {v}"
            size = 30 if etype in ("Category", "Segment", "Region") else \
                   20 if etype in ("SubCategory", "PriceTier", "ShipMode") else \
                   10 if etype == "Product" else 15
            net.add_node(nid, label=label, title=title, color=color, size=size,
                         shape="dot" if etype != "Segment" else "star")
            added.add(nid)

    edge_count = 0
    for src, dst, data in kb.G.edges(data=True):
        if src in added and dst in added:
            label = data.get("label", "")
            if show_edges and label:
                net.add_edge(src, dst, title=label, label=label,
                             font={"size": 8, "align": "middle"})
            else:
                net.add_edge(src, dst, title=label if show_edges else "")
            edge_count += 1

    # Highlight target if searched
    if target_id and target_id in added:
        net.add_node(target_id, color="#FF0000", size=35, borderWidth=4)

    # Save and render
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as f:
        net.save_graph(f.name)
        with open(f.name, "r") as fh:
            html = fh.read()
        os.unlink(f.name)

    components.html(html, height=700)

    st.caption(f"Showing {len(added)} nodes, {edge_count} edges. "
               f"Click a node to inspect its attributes. Search above to focus on a specific entity.")

    # Inspector panel
    if target_id:
        st.subheader("🔍 Entity Inspector")
        attrs = kb.get_entity(target_id)
        if attrs:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"**ID:** `{target_id}`")
                st.markdown(f"**Type:** {attrs.get('type', '—')}")
                st.markdown(f"**Name:** {attrs.get('name', '—')}")
            with col2:
                st.json({k: v for k, v in attrs.items() if k not in ("type", "name")})

            neighbors = kb.get_neighbors(target_id)
            if neighbors:
                st.markdown("**Relations:**")
                for nid, nattrs, label in neighbors:
                    ntype = nattrs.get("type", "?")
                    nname = nattrs.get("name", nid)
                    st.markdown(f" — **{label}** → `{nname}` ({ntype})")


# ═══════════════════════════════════════════════════════════════════
# PAGE 2: ENTITY BROWSER
# ═══════════════════════════════════════════════════════════════════
elif "Entity Browser" in page:
    st.title("🔍 Entity Browser")
    st.markdown("Browse all entities in the knowledge base by type.")

    c1, c2 = st.columns([1, 2])
    types = kb.get_entity_types()
    sel_type = c1.selectbox("Entity type", sorted(types), key="eb_type")

    search = c2.text_input("Search within type", placeholder="name or ID...", key="eb_search")

    entities = kb.get_all_of_type(sel_type, limit=1000)
    if search:
        q = search.lower()
        entities = [(nid, a) for nid, a in entities if q in nid.lower() or q in a.get("name", "").lower()]

    if entities:
        df = pd.DataFrame([
            {"ID": nid, "Name": a.get("name", ""), **{k: v for k, v in a.items() if k not in ("type", "name")}}
            for nid, a in entities
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{len(df)} entities")
    else:
        st.info("No entities found.")

    # Click to inspect
    st.subheader("Inspect Entity")
    eid = st.text_input("Entity ID (click the ID above, or paste here)", key="eb_inspect")
    if eid and eid in kb.G:
        attrs = kb.get_entity(eid)
        st.json(attrs)
        neighbors = kb.get_neighbors(eid)
        if neighbors:
            st.markdown("**Relations:**")
            for nid, nattrs, label in neighbors:
                st.markdown(f" — **{label}** → `{nattrs.get('name', nid)}` ({nattrs.get('type', '?')})")
    elif eid:
        st.warning("Entity not found in the knowledge base.")


# ═══════════════════════════════════════════════════════════════════
# PAGE 3: RULE ENGINE
# ═══════════════════════════════════════════════════════════════════
elif "Rule Engine" in page:
    st.title("⚙️ Rule Engine")
    st.markdown("Symbolic rules that power recommendations. Each rule is a set of logical conditions → actions.")

    tab1, tab2, tab3 = st.tabs(["📋 All Rules", "🧪 Test on a Customer", "➕ New Rule (Preview)"])

    with tab1:
        for i, rule in enumerate(RULES):
            with st.expander(f"**{rule.name}** (strength={rule.strength})", expanded=i < 3):
                st.markdown(f"*{rule.description}*")
                st.markdown("**Conditions:**")
                for cond in rule.conditions:
                    op_symbol = {"eq": "==", "neq": "!=", "in": "∈", "gt": ">", "lt": "<",
                                 "has_bought": "✓", "not_bought": "✗"}.get(cond.op, cond.op)
                    st.code(f"  {cond.attribute} {op_symbol} {cond.value}")
                st.markdown("**Actions:**")
                for a in rule.actions:
                    params = ", ".join(f"{k}={v}" for k, v in a.params.items())
                    st.code(f"  ⮕ {a.action_type} → {a.target}  ({params})")
                st.markdown(f"**Reason:** _{rule.reason_template}_")

    with tab2:
        st.markdown("Select a customer and see which rules fire.")

        # Customer selector
        con = kb.con
        custs = pd.read_sql_query("""
            SELECT c.Customer_ID, c.Customer_Name, ROUND(SUM(od.Sales),0) AS total_sales
            FROM customers c
            JOIN orders o ON o.Customer_ID = c.Customer_ID
            JOIN order_details od ON od.Order_ID = o.Order_ID
            GROUP BY c.Customer_ID
            ORDER BY total_sales DESC LIMIT 100
        """, con)

        cust_options = {f"{r['Customer_Name']} (${r['total_sales']:,.0f})": r['Customer_ID']
                       for _, r in custs.iterrows()}
        selected_cust = st.selectbox("Choose a customer", list(cust_options.keys()), key="test_cust")
        cust_id = cust_options[selected_cust]

        if st.button("▶️ Run Rules", type="primary", key="run_rules"):
            facts = build_customer_facts(kb, cust_id)
            if facts:
                st.subheader("Customer Facts")
                st.json({k: v for k, v in facts.items() if not k.startswith("_")})

                results = engine.infer(facts)
                if results:
                    st.subheader(f"✅ {len(results)} Rules Fired")
                    for rule, actions, reason in results:
                        with st.container(border=True):
                            st.markdown(f"**{rule.name}** (confidence: {rule.strength:.0%})")
                            st.markdown(f"📝 {reason}")
                            for a in actions:
                                st.info(f"⮕ **{a.action_type.upper()}**: {a.target}" +
                                        (f" (discount: {a.params.get('discount', 'N/A')})" if a.params else ""))
                else:
                    st.info("No rules fired for this customer.")
            else:
                st.error("Could not build facts for this customer.")

    with tab3:
        st.markdown("**Rule creator** *(concept — rules are Python dataclasses)*")
        st.code("""Rule(
    name="My Custom Rule",
    description="What this rule does",
    conditions=[
        Condition("segment", "eq", "Corporate"),
        Condition("clv_tier", "in", ["Gold", "Silver"]),
    ],
    actions=[Action("recommend", "category:Furniture",
                    params={"discount": 0.10})],
    strength=0.8,
    reason_template="Custom reason for {segment} customers."
)""", language="python")
        st.markdown("Edit `rule_engine.py` to add/modify rules, then restart the app.")


# ═══════════════════════════════════════════════════════════════════
# PAGE 4: SYMBOL DICTIONARY
# ═══════════════════════════════════════════════════════════════════
elif "Symbol Dictionary" in page:
    st.title("📖 Symbol Dictionary")
    st.markdown("The **vocabulary** of the knowledge base — all symbolic values and where they're used.")

    symbols = kb.get_symbols()

    # Overview table
    rows = []
    for sym_name, values in symbols.items():
        rows.append({"Symbol": sym_name, "Possible Values": ", ".join(values), "Count": len(values)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Detail per symbol
    for sym_name, values in symbols.items():
        with st.expander(f"**{sym_name}** ({len(values)} values)"):
            for val in values:
                # Count entities using this symbol
                count = 0
                for _, attrs in kb.G.nodes(data=True):
                    for k, v in attrs.items():
                        if isinstance(v, str) and v.lower() == val.lower():
                            count += 1
                st.markdown(f"**`{val}`** — used in {count} entities")

    # Symbol usage in rules
    st.markdown("---")
    st.subheader("Symbol Usage in Rules")
    sym_in_rules = {}
    for rule in RULES:
        for cond in rule.conditions:
            sym_in_rules.setdefault(cond.attribute, set()).add(rule.name)

    rows2 = []
    for attr, rule_names in sorted(sym_in_rules.items()):
        rows2.append({"Attribute": attr, "Used in Rules": ", ".join(sorted(rule_names))})
    st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)
