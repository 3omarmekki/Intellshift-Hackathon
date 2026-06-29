"""
Symbolic Rule Engine v2 for the Superstore Recommendation System.

Fixes vs v1:
  - Condition evaluation properly supports dict-valued facts via `sub_attr`,
    so "has this customer bought subcategory X" and "days since subcat Y"
    actually check X / Y specifically, instead of v1's bug where
    `has_bought_subcategory` / `not_bought_subcategory` were single keys
    overwritten on every loop iteration (only the last subcategory mattered).
  - Hand-authored rules now sit alongside AUTO-MINED rules (from mining.py's
    Apriori output), so cross-sell rules aren't limited to the ones someone
    thought to hardcode.
  - Multiple matched rules per customer are combined into a single ranked
    score per recommended target using noisy-OR (see RecommendationEngine
    docstring below) instead of just being listed unranked.
"""

from dataclasses import dataclass, field
from datetime import datetime
from math import log

from mining import generate_association_rules, AssociationRule


# ───────────────────────────── DSL ─────────────────────────────

@dataclass
class Condition:
    attribute: str        # key into the facts dict, e.g. "segment", "clv_tier",
                           # "bought_subcategories", "days_since_subcat"
    op: str                # "eq" "neq" "in" "gt" "lt" "gte" "lte" "has_bought" "not_bought"
    value: object
    sub_attr: str = ""     # if facts[attribute] is a dict/set, look inside it
                           # e.g. attribute="days_since_subcat", sub_attr="Paper"


@dataclass
class Action:
    action_type: str      # "recommend" "campaign" "alert" "discount"
    target: str
    params: dict = field(default_factory=dict)


@dataclass
class Rule:
    name: str
    description: str
    conditions: list
    actions: list
    strength: float = 1.0          # base confidence, hand-tuned or from mining
    reason_template: str = ""
    source: str = "manual"         # "manual" | "mined"
    lift: float = 1.0              # only meaningful for mined rules; used in scoring


def _resolve(cond: Condition, facts: dict):
    """Pull the value a condition should test, drilling into a sub_attr if given."""
    val = facts.get(cond.attribute)
    if cond.sub_attr:
        if isinstance(val, dict):
            return val.get(cond.sub_attr)
        return None
    return val


def _eval_cond(cond: Condition, facts: dict) -> bool:
    if cond.op in ("has_bought", "not_bought"):
        bought = facts.get("bought_subcategories", set())
        is_in = cond.value in bought
        return is_in if cond.op == "has_bought" else not is_in

    val = _resolve(cond, facts)

    if cond.op == "eq":
        return str(val).lower() == str(cond.value).lower()
    elif cond.op == "neq":
        return str(val).lower() != str(cond.value).lower()
    elif cond.op == "in":
        return str(val).lower() in [str(v).lower() for v in cond.value]
    elif cond.op in ("gt", "lt", "gte", "lte"):
        try:
            fv, cv = float(val), float(cond.value)
        except (TypeError, ValueError):
            return False
        return {"gt": fv > cv, "lt": fv < cv, "gte": fv >= cv, "lte": fv <= cv}[cond.op]
    return False


# ───────────────────────── Hand-authored rules ─────────────────────────

RULES = [
    Rule(
        name="Complete the Office Suite",
        description="Customer bought Chairs -> recommend Desks",
        conditions=[
            Condition("category_affinity", "eq", "Furniture"),
            Condition("bought_subcategories", "has_bought", "Chairs"),
            Condition("bought_subcategories", "not_bought", "Desks"),
        ],
        actions=[Action("recommend", "subcategory:Desks", params={"filter_category": "Furniture"})],
        strength=0.9,
        reason_template="You bought {chairs_product}, complete your workspace with a matching desk.",
    ),
    Rule(
        name="Consumable Companion",
        description="Bought Binders -> recommend Paper",
        conditions=[
            Condition("bought_subcategories", "has_bought", "Binders"),
            Condition("bought_subcategories", "not_bought", "Paper"),
        ],
        actions=[Action("recommend", "subcategory:Paper", params={"filter_category": "Office Supplies"})],
        strength=0.85,
        reason_template="Binders need filling — stock up on paper to stay organized.",
    ),
    Rule(
        name="Work-From-Home Setup",
        description="Bought a Phone -> recommend Headset",
        conditions=[
            Condition("bought_subcategories", "has_bought", "Phones"),
            Condition("bought_subcategories", "not_bought", "Headsets"),
        ],
        actions=[Action("recommend", "subcategory:Headsets", params={"filter_category": "Technology"})],
        strength=0.75,
        reason_template="You bought a phone — a headset makes every call hands-free.",
    ),
    Rule(
        name="Upgrade Your Chair",
        description="Frequent Corporate chair buyer -> recommend Premium chairs",
        conditions=[
            Condition("segment", "eq", "Corporate"),
            Condition("frequency_tier", "eq", "High"),
            Condition("bought_subcategories", "has_bought", "Chairs"),
        ],
        actions=[Action("recommend", "upsell:Chairs", params={"target_tier": "Premium"})],
        strength=0.7,
        reason_template="As a frequent Corporate buyer, you deserve premium comfort.",
    ),
    Rule(
        name="Tech Upgrade Path",
        description="Tech affinity + high CLV -> recommend Premium Tech",
        conditions=[
            Condition("category_affinity", "eq", "Technology"),
            Condition("clv_tier", "in", ["Silver", "Gold"]),
        ],
        actions=[Action("recommend", "upsell:Technology", params={"target_tier": "Premium"})],
        strength=0.65,
        reason_template="Upgrade your tech setup with our premium selection.",
    ),
    Rule(
        name="Restock Paper",
        description="Bought Paper > 90 days ago",
        conditions=[
            Condition("bought_subcategories", "has_bought", "Paper"),
            Condition("days_since_subcat", "gt", 90, sub_attr="Paper"),
        ],
        actions=[Action("recommend", "subcategory:Paper",
                         params={"filter_category": "Office Supplies", "discount": 0.10})],
        strength=0.95,
        reason_template="It's been a while since your last paper purchase — time to restock!",
    ),
    Rule(
        name="Restock Binders",
        description="Bought Binders > 180 days ago",
        conditions=[
            Condition("bought_subcategories", "has_bought", "Binders"),
            Condition("days_since_subcat", "gt", 180, sub_attr="Binders"),
        ],
        actions=[Action("recommend", "subcategory:Binders",
                         params={"filter_category": "Office Supplies", "discount": 0.10})],
        strength=0.9,
        reason_template="Binders running low? Here's 10% off to restock.",
    ),
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
        reason_template="Year-end budgets — refresh your office with 15% off furniture.",
    ),
    Rule(
        name="Home Office Spring Setup",
        description="Home Office segment in spring -> Furniture + Technology",
        conditions=[
            Condition("segment", "eq", "Home Office"),
            Condition("month", "in", [3, 4, 5]),
        ],
        actions=[Action("campaign", "Spring Home Office Refresh",
                         params={"category": "all", "discount": 0.10})],
        strength=0.7,
        reason_template="Spring is here — refresh your home office with 10% off.",
    ),
    Rule(
        name="VIP Win-Back",
        description="Gold CLV, inactive > 180 days",
        conditions=[
            Condition("clv_tier", "eq", "Gold"),
            Condition("days_since_last", "gt", 180),
        ],
        actions=[Action("campaign", "VIP We Miss You", params={"discount": 0.25})],
        strength=0.9,
        reason_template="We miss you! Here's 25% off your next order — our VIP thanks.",
    ),
    Rule(
        name="Active VIP — Exclusive Early Access",
        description="Gold CLV, active recently",
        conditions=[
            Condition("clv_tier", "eq", "Gold"),
            Condition("recency_tier", "eq", "Active"),
        ],
        actions=[Action("campaign", "VIP Early Access", params={"discount": 0.20, "exclusive": True})],
        strength=0.7,
        reason_template="Exclusive VIP early access — 20% off before everyone else.",
    ),
    Rule(
        name="Corporate Tech Accessories",
        description="Corporate + tech affinity -> recommend accessories",
        conditions=[
            Condition("segment", "eq", "Corporate"),
            Condition("category_affinity", "eq", "Technology"),
        ],
        actions=[Action("recommend", "subcategory:Accessories", params={"filter_category": "Technology"})],
        strength=0.75,
        reason_template="Equip your team with the latest tech accessories.",
    ),
    Rule(
        name="Consumer — Expand Categories",
        description="Consumer buying only Office Supplies -> explore Furniture",
        conditions=[
            Condition("segment", "eq", "Consumer"),
            Condition("category_affinity", "eq", "Office Supplies"),
        ],
        actions=[Action("recommend", "category:Furniture", params={"discount": 0.10})],
        strength=0.6,
        reason_template="You love Office Supplies — discover our Furniture collection, 10% off.",
    ),
]


# ───────────────────────── Auto-mining -> Rule objects ─────────────────────────

def mined_rules_from_baskets(baskets, min_support=0.01, min_confidence=0.2,
                              min_lift=1.1, max_k=3, max_rules=50):
    """Convert Apriori AssociationRules into Rule objects so they can be
    forward-chained exactly like hand-authored rules.

    Only single-item -> single-item rules become "has_bought(A) -> recommend B"
    conditions (multi-item antecedents are supported by chaining `has_bought`
    conditions for every item in A).
    strength is set from confidence; `lift` is carried through for scoring.
    """
    assoc_rules = generate_association_rules(
        baskets, min_support=min_support, min_confidence=min_confidence,
        min_lift=min_lift, max_k=max_k,
    )

    out = []
    for ar in assoc_rules[:max_rules]:
        if len(ar.consequent) != 1:
            continue  # keep recommendations single-target for clarity
        target = next(iter(ar.consequent))
        conditions = [Condition("bought_subcategories", "has_bought", a) for a in ar.antecedent]
        conditions.append(Condition("bought_subcategories", "not_bought", target))
        a_label = " + ".join(sorted(ar.antecedent))
        out.append(Rule(
            name=f"[Mined] {a_label} -> {target}",
            description=f"Apriori: support={ar.support:.3f}, confidence={ar.confidence:.3f}, lift={ar.lift:.2f}",
            conditions=conditions,
            actions=[Action("recommend", f"subcategory:{target}",
                             params={"support": ar.support, "confidence": ar.confidence, "lift": ar.lift})],
            strength=round(ar.confidence, 3),
            reason_template=f"Customers who buy {a_label} also tend to buy {target} "
                             f"(lift {ar.lift:.1f}x baseline).",
            source="mined",
            lift=ar.lift,
        ))
    return out


# ───────────────────────── Inference + Scoring Engine ─────────────────────────

class InferenceEngine:
    def __init__(self, rules=None):
        self.rules = rules or RULES

    def infer(self, customer_facts):
        results = []
        for rule in self.rules:
            if all(_eval_cond(c, customer_facts) for c in rule.conditions):
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
        return next((r for r in self.rules if r.name == rule_name), None)


class RecommendationEngine:
    """
    Combines every matched rule into a single ranked list of targets.

    ─────────────────── THE MATH: noisy-OR combination ───────────────────
    Treat each matched rule i recommending the same target as independent
    evidence that the target is "worth recommending", with probability of
    being a true positive ≈ its effective strength p_i ∈ [0, 1].

    For mined rules, p_i is scaled by lift to reward associations that are
    not just frequent but disproportionately stronger than baseline:

        p_i = min(1, strength_i * log(1 + lift_i))   if source == "mined"
        p_i = strength_i                              if source == "manual"

    (log(1+lift) so lift=1 i.e. "no extra signal" contributes a damped
    ~0.69x multiplier rather than passing strength through unchanged, and
    very high lift saturates rather than blowing up the score.)

    Combining k independent pieces of positive evidence via noisy-OR:

        P(at least one rule is "right") = 1 - Π_i (1 - p_i)

    This is the natural probabilistic combination for "evidence stacks":
    it never exceeds 1, increases monotonically as more rules agree, and
    a single very strong rule (p_i close to 1) dominates regardless of how
    many weak rules also fired — matching the business intuition that 5
    weak hints shouldn't outrank 1 near-certain signal as hard as a naive
    sum would.
    ────────────────────────────────────────────────────────────────────
    """

    def __init__(self, engine: InferenceEngine = None):
        self.engine = engine or InferenceEngine()

    def _effective_strength(self, rule: Rule) -> float:
        if rule.source == "mined":
            return min(1.0, rule.strength * log(1 + rule.lift))
        return rule.strength

    def recommend(self, customer_facts, top_n=5):
        matches = self.engine.infer(customer_facts)

        by_target = {}  # target -> list of (rule, reason, p_i)
        for rule, actions, reason in matches:
            for action in actions:
                key = (action.action_type, action.target)
                p_i = self._effective_strength(rule)
                by_target.setdefault(key, []).append((rule, reason, p_i))

        scored = []
        for (action_type, target), evidence in by_target.items():
            probs = [p for _, _, p in evidence]
            combined = 1.0
            for p in probs:
                combined *= (1 - p)
            score = 1 - combined  # noisy-OR
            top_reason = max(evidence, key=lambda e: e[2])[1]
            contributing = [r.name for r, _, _ in evidence]
            scored.append({
                "action_type": action_type,
                "target": target,
                "score": round(score, 4),
                "reason": top_reason,
                "rules": contributing,
                "n_rules": len(evidence),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]


# ───────────────────────── Fact-building from the KB ─────────────────────────

def build_customer_facts(kb, customer_id):
    """Build a fact dict for a customer from the knowledge base (v2: uses the
    KB's precomputed per-customer subcategory stats instead of the v1 loop bug)."""
    cust = kb.get_entity(f"cust:{customer_id}")
    if not cust:
        return None

    subcat_stats = kb.customer_subcat_stats.get(customer_id, {})

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
        "bought_subcategories": set(subcat_stats.keys()),
        "days_since_subcat": {sc: v["days_since"] for sc, v in subcat_stats.items()},
        "subcat_spend": {sc: v["total"] for sc, v in subcat_stats.items()},
    }

    # For reason templates like "{chairs_product}"
    facts["chairs_product"] = ""
    for nid, attrs, edata in kb.get_neighbors(f"cust:{customer_id}"):
        if attrs.get("type") == "Product" and attrs.get("sub_category") == "Chairs":
            facts["chairs_product"] = attrs.get("name", "a chair")
            break

    return facts


if __name__ == "__main__":
    # Self-contained smoke test (no DB needed): mined rules from synthetic baskets
    # combined with hand-authored rules, scored via noisy-OR.
    sample_baskets = [
        {"Chairs", "Desks"}, {"Chairs", "Desks"}, {"Chairs", "Paper"},
        {"Paper", "Binders"}, {"Chairs", "Desks"}, {"Binders", "Paper"},
        {"Phones", "Headsets"}, {"Chairs"}, {"Desks"}, {"Paper"},
    ] * 5

    mined = mined_rules_from_baskets(sample_baskets, min_support=0.05, min_confidence=0.3, min_lift=1.0)
    all_rules = RULES + mined
    print(f"{len(RULES)} manual rules + {len(mined)} mined rules = {len(all_rules)} total\n")

    sample_facts = {
        "segment": "Corporate",
        "clv_tier": "Gold",
        "recency_tier": "Active",
        "frequency_tier": "High",
        "category_affinity": "Furniture",
        "days_since_last": 15,
        "month": 11,
        "bought_subcategories": {"Chairs", "Paper"},
        "days_since_subcat": {"Paper": 120, "Binders": 999},
        "chairs_product": "Global Deluxe Office Chair",
    }

    rec_engine = RecommendationEngine(InferenceEngine(all_rules))
    for rec in rec_engine.recommend(sample_facts, top_n=10):
        print(f"  [{rec['score']:.3f}] {rec['action_type']}: {rec['target']}  "
              f"(from {rec['n_rules']} rule(s): {', '.join(rec['rules'])})")
        print(f"          \u2192 {rec['reason']}\n")
