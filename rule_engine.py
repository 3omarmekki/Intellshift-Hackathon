"""
Symbolic Rule Engine for Superstore Recommendation System.

Each Rule has:
  - name:        human-readable label
  - description: what it does
  - conditions:  list of (attribute, operator, value) triples
  - actions:     list of actions (recommend_product, campaign, etc.)
  - strength:    0.0–1.0 confidence weight
  - reason_template: string with {placeholders} for explanation

Inference: forward-chaining over a customer fact dict.
"""

from dataclasses import dataclass, field
from typing import Callable
import re
from datetime import datetime


@dataclass
class Condition:
    attribute: str       # e.g. "segment", "clv_tier", "category_affinity"
    op: str              # "eq", "neq", "in", "gt", "lt", "has_bought", "not_bought"
    value: object        # e.g. "Corporate", "Gold", ["Furniture", "Technology"]
    sub_attr: str = ""   # for nested fact access


@dataclass
class Action:
    action_type: str     # "recommend", "campaign", "alert", "discount"
    target: str          # e.g. product category, sub_category, campaign name
    params: dict = field(default_factory=dict)


@dataclass
class Rule:
    name: str
    description: str
    conditions: list
    actions: list
    strength: float = 1.0
    reason_template: str = ""


# ── Helper to evaluate a single condition against customer facts ──
def _eval_cond(cond, facts):
    val = facts.get(cond.attribute)
    if cond.op == "eq":
        return str(val).lower() == str(cond.value).lower()
    elif cond.op == "neq":
        return str(val).lower() != str(cond.value).lower()
    elif cond.op == "in":
        return str(val).lower() in [str(v).lower() for v in cond.value]
    elif cond.op == "gt":
        try:
            return float(val) > float(cond.value)
        except (TypeError, ValueError):
            return False
    elif cond.op == "lt":
        try:
            return float(val) < float(cond.value)
        except (TypeError, ValueError):
            return False
    elif cond.op == "has_bought":
        bought = facts.get("products_bought", set())
        return cond.value in bought
    elif cond.op == "not_bought":
        bought = facts.get("products_bought", set())
        return cond.value not in bought
    return False


# ── Rule definitions ──

RULES = [
    # ── Cross-sell ──
    Rule(
        name="Complete the Office Suite",
        description="Customer bought Chairs → recommend Desks",
        conditions=[
            Condition("category_affinity", "eq", "Furniture"),
            Condition("has_bought_subcategory", "eq", "Chairs"),
            Condition("not_bought_subcategory", "eq", "Desks"),
        ],
        actions=[Action("recommend", "subcategory:Desks",
                        params={"filter_category": "Furniture"})],
        strength=0.9,
        reason_template="You bought {chairs_product}, complete your workspace with a matching desk."
    ),
    Rule(
        name="Consumable Companion",
        description="Bought Binders → recommend Paper",
        conditions=[
            Condition("has_bought_subcategory", "eq", "Binders"),
            Condition("not_bought_subcategory", "eq", "Paper"),
        ],
        actions=[Action("recommend", "subcategory:Paper",
                        params={"filter_category": "Office Supplies"})],
        strength=0.85,
        reason_template="Binders need filling — stock up on paper to stay organized."
    ),
    Rule(
        name="Work-From-Home Setup",
        description="Bought a Phone → recommend Headset",
        conditions=[
            Condition("has_bought_subcategory", "eq", "Phones"),
            Condition("not_bought_subcategory", "eq", "Headsets"),
        ],
        actions=[Action("recommend", "subcategory:Headsets",
                        params={"filter_category": "Technology"})],
        strength=0.75,
        reason_template="You bought a phone — a headset makes every call hands-free."
    ),

    # ── Upsell ──
    Rule(
        name="Upgrade Your Chair",
        description="Customer bought Budget chairs frequently → recommend Premium chairs",
        conditions=[
            Condition("segment", "eq", "Corporate"),
            Condition("frequency_tier", "eq", "High"),
            Condition("has_bought_subcategory", "eq", "Chairs"),
        ],
        actions=[Action("recommend", "upsell:Chairs",
                        params={"target_tier": "Premium"})],
        strength=0.7,
        reason_template="As a frequent Corporate buyer, you deserve premium comfort."
    ),
    Rule(
        name="Tech Upgrade Path",
        description="Bought Mid-tier Tech → recommend Premium Tech",
        conditions=[
            Condition("category_affinity", "eq", "Technology"),
            Condition("clv_tier", "in", ["Silver", "Gold"]),
        ],
        actions=[Action("recommend", "upsell:Technology",
                        params={"target_tier": "Premium"})],
        strength=0.65,
        reason_template="Upgrade your tech setup with our premium selection."
    ),

    # ── Replenishment ──
    Rule(
        name="Restock Paper",
        description="Customer bought Paper > 90 days ago",
        conditions=[
            Condition("has_bought_subcategory", "eq", "Paper"),
            Condition("days_since_paper_purchase", "gt", 90),
        ],
        actions=[Action("recommend", "subcategory:Paper",
                        params={"filter_category": "Office Supplies",
                                "discount": 0.10})],
        strength=0.95,
        reason_template="It's been a while since your last paper purchase — time to restock!"
    ),
    Rule(
        name="Restock Binders",
        description="Customer bought Binders > 180 days ago",
        conditions=[
            Condition("has_bought_subcategory", "eq", "Binders"),
            Condition("days_since_binders_purchase", "gt", 180),
        ],
        actions=[Action("recommend", "subcategory:Binders",
                        params={"filter_category": "Office Supplies",
                                "discount": 0.10})],
        strength=0.9,
        reason_template="Binders running low? Here's 10% off to restock."
    ),

    # ── Seasonal / Campaign ──
    Rule(
        name="Year-End Furniture Push",
        description="Corporate customers get furniture offers in Q4",
        conditions=[
            Condition("segment", "eq", "Corporate"),
            Condition("month", "in", [10, 11, 12]),
        ],
        actions=[Action("campaign", "Year-End Office Refresh",
                        params={"category": "Furniture", "discount": 0.15})],
        strength=0.8,
        reason_template="Year-end budgets — refresh your office with 15% off furniture."
    ),
    Rule(
        name="Home Office Spring Setup",
        description="Home Office segment in spring → recommend Furniture + Technology",
        conditions=[
            Condition("segment", "eq", "Home Office"),
            Condition("month", "in", [3, 4, 5]),
        ],
        actions=[Action("campaign", "Spring Home Office Refresh",
                        params={"category": "all", "discount": 0.10})],
        strength=0.7,
        reason_template="Spring is here — refresh your home office with 10% off."
    ),

    # ── VIP / Retention ──
    Rule(
        name="VIP Win-Back",
        description="Gold CLV, inactive > 180 days",
        conditions=[
            Condition("clv_tier", "eq", "Gold"),
            Condition("days_since_last", "gt", 180),
        ],
        actions=[Action("campaign", "VIP We Miss You",
                        params={"discount": 0.25})],
        strength=0.9,
        reason_template="We miss you! Here's 25% off your next order — our VIP thanks."
    ),
    Rule(
        name="Active VIP — Exclusive Early Access",
        description="Gold CLV, active recently",
        conditions=[
            Condition("clv_tier", "eq", "Gold"),
            Condition("recency_tier", "eq", "Active"),
        ],
        actions=[Action("campaign", "VIP Early Access",
                        params={"discount": 0.20, "exclusive": True})],
        strength=0.7,
        reason_template="Exclusive VIP early access — 20% off before everyone else."
    ),

    # ── Segment-specific Targeting ──
    Rule(
        name="Corporate Tech Accessories",
        description="Corporate segment with tech affinity → recommend accessories",
        conditions=[
            Condition("segment", "eq", "Corporate"),
            Condition("category_affinity", "eq", "Technology"),
        ],
        actions=[Action("recommend", "subcategory:Accessories",
                        params={"filter_category": "Technology"})],
        strength=0.75,
        reason_template="Equip your team with the latest tech accessories."
    ),
    Rule(
        name="Consumer — Expand Categories",
        description="Consumer buying only Office Supplies → explore Furniture",
        conditions=[
            Condition("segment", "eq", "Consumer"),
            Condition("category_affinity", "eq", "Office Supplies"),
        ],
        actions=[Action("recommend", "category:Furniture",
                        params={"discount": 0.10})],
        strength=0.6,
        reason_template="You love Office Supplies — discover our Furniture collection, 10% off."
    ),
]


# ── Inference Engine ──
class InferenceEngine:
    def __init__(self, rules=None):
        self.rules = rules or RULES

    def infer(self, customer_facts):
        """
        customer_facts: dict with keys like segment, clv_tier, recency_tier,
                        frequency_tier, category_affinity, days_since_last,
                        products_bought (set of sub-category names),
                        days_since_{subcat}_purchase, month
        Returns list of (rule, actions_matched, reason)
        """
        results = []
        for rule in self.rules:
            matched = True
            for cond in rule.conditions:
                if not _eval_cond(cond, customer_facts):
                    matched = False
                    break
            if matched:
                reason = self._render_reason(rule, customer_facts)
                results.append((rule, rule.actions, reason))
        return results

    def _render_reason(self, rule, facts):
        if not rule.reason_template:
            return rule.description
        try:
            return rule.reason_template.format(**facts)
        except KeyError:
            return rule.description

    def explain_rule(self, rule_name):
        for r in self.rules:
            if r.name == rule_name:
                return r
        return None


def build_customer_facts(kb, customer_id):
    """Build a fact dict for a customer from the knowledge base."""
    cust = kb.get_entity(f"cust:{customer_id}")
    if not cust:
        return None

    facts = {
        "segment": cust.get("segment", ""),
        "clv_tier": cust.get("clv_tier", ""),
        "recency_tier": cust.get("recency_tier", ""),
        "frequency_tier": cust.get("frequency_tier", ""),
        "category_affinity": cust.get("category_affinity", ""),
        "total_spent": cust.get("total_spent", 0),
        "order_count": cust.get("order_count", 0),
        "days_since_last": cust.get("days_since_last", 999),
        "month": datetime.now().month,
    }

    # Products / sub-categories bought
    neighbors = kb.get_neighbors(f"cust:{customer_id}")
    bought_subcats = set()
    days_since_purchase = {}
    for nid, attrs, label in neighbors:
        if attrs.get("type") == "Product":
            sc = attrs.get("sub_category", "")
            if sc:
                bought_subcats.add(sc)
            # Extract product name for templates
            facts.setdefault("chairs_product", "")
            if sc == "Chairs" and not facts["chairs_product"]:
                facts["chairs_product"] = attrs.get("name", "a chair")

    facts["products_bought"] = bought_subcats
    for sc in bought_subcats:
        facts[f"has_bought_subcategory"] = sc
        facts[f"not_bought_subcategory"] = sc
    # This is simplified — in production we'd track per-subcat timestamps

    # For the rule evaluation we need has_bought / not_bought to work on specific values
    # Let's add helper keys
    for sc in ["Chairs", "Desks", "Paper", "Binders", "Phones", "Headsets",
               "Accessories", "Furnishings", "Tables", "Bookcases"]:
        facts[f"has_bought_{sc.lower()}"] = sc in bought_subcats
        facts[f"days_since_{sc.lower()}_purchase"] = 30 if sc in bought_subcats else 999

    return facts


if __name__ == "__main__":
    from datetime import datetime

    # Test with a sample customer fact set
    sample = {
        "segment": "Corporate",
        "clv_tier": "Gold",
        "recency_tier": "Active",
        "frequency_tier": "High",
        "category_affinity": "Furniture",
        "days_since_last": 15,
        "month": 11,
        "products_bought": {"Chairs", "Paper"},
        "chairs_product": "Global Deluxe Office Chair",
        "has_bought_chairs": True,
        "has_bought_desks": False,
        "has_bought_paper": True,
        "has_bought_binders": False,
        "days_since_paper_purchase": 120,
        "days_since_binders_purchase": 999,
    }

    engine = InferenceEngine()
    results = engine.infer(sample)
    print(f"Inferred {len(results)} rules for sample customer:\n")
    for rule, actions, reason in results:
        print(f"  RULE: {rule.name} (strength={rule.strength})")
        for a in actions:
            print(f"    → {a.action_type}: {a.target}")
        print(f"    ⓘ {reason}\n")
