"""
Association Rule Mining (Apriori) over Superstore order baskets.

────────────────────────────────────────────────────────────────────────────
THE MATH
────────────────────────────────────────────────────────────────────────────

Let D be the set of N transactions (here: orders), each a set of items
(here: sub-categories purchased together, e.g. {"Chairs", "Paper"}).

For an itemset X ⊆ items:

    support(X) = |{ t ∈ D : X ⊆ t }| / |D|

    i.e. the fraction of orders that contain ALL items in X.
    This is a *probability estimate*: support(X) ≈ P(X all bought together).

Apriori exploits the anti-monotonicity (downward-closure) property:

    X ⊆ Y  ⟹  support(X) ≥ support(Y)

i.e. if a SUPERSET is frequent, all its SUBSETS must also be frequent.
Contrapositive: if X is NOT frequent, no superset of X can be frequent.
This lets us prune the search space level-by-level instead of enumerating
all 2^n subsets:

    L1 = {single items with support ≥ min_support}
    L2 = {pairs built ONLY from items in L1, with support ≥ min_support}
    L3 = {triples built ONLY from items in L2, ...}
    ... stop when L_k is empty.

For an association rule  A → B  (A, B disjoint itemsets):

    confidence(A → B) = support(A ∪ B) / support(A)
                       = P(B | A)   (empirical conditional probability)

    lift(A → B) = confidence(A → B) / support(B)
                = P(A ∪ B) / ( P(A) · P(B) )

    Interpretation of lift:
        lift = 1   → A and B are statistically independent (no signal)
        lift > 1   → buying A makes buying B MORE likely than baseline
                      (positive association — good for cross-sell)
        lift < 1   → buying A makes buying B LESS likely (substitutes)

    conviction(A → B) = (1 - support(B)) / (1 - confidence(A → B))
        A more robust alternative to confidence — corrects for how
        common B is. conviction → ∞ as confidence → 1; conviction = 1
        when A, B independent (no association, same info as lift=1).

A rule only becomes a candidate recommendation when it clears BOTH a
support floor (it's common enough to be statistically reliable, not
noise from 2 orders) and a confidence/lift floor (the association is
strong and positive, not coincidental or negative).
────────────────────────────────────────────────────────────────────────────
"""

from dataclasses import dataclass
from itertools import combinations
from typing import FrozenSet, List


@dataclass(frozen=True)
class FrequentItemset:
    items: FrozenSet[str]
    support: float
    count: int


@dataclass(frozen=True)
class AssociationRule:
    antecedent: FrozenSet[str]   # A
    consequent: FrozenSet[str]   # B
    support: float               # support(A ∪ B)
    confidence: float            # P(B | A)
    lift: float                  # P(A∪B) / (P(A)P(B))
    conviction: float

    def __repr__(self):
        a = ", ".join(sorted(self.antecedent))
        b = ", ".join(sorted(self.consequent))
        return (f"{a} -> {b}  "
                f"(support={self.support:.3f}, confidence={self.confidence:.3f}, "
                f"lift={self.lift:.2f})")


def _support_of(itemset, baskets):
    n = len(baskets)
    if n == 0:
        return 0.0, 0
    cnt = sum(1 for b in baskets if itemset <= b)
    return cnt / n, cnt


def apriori_frequent_itemsets(baskets: List[set], min_support: float = 0.01,
                               max_k: int = 3) -> List[FrequentItemset]:
    """Standard level-wise Apriori. Returns ALL frequent itemsets (sizes 1..max_k)."""
    n = len(baskets)
    if n == 0:
        return []

    # L1: frequent single items
    item_counts = {}
    for b in baskets:
        for it in b:
            item_counts[it] = item_counts.get(it, 0) + 1
    current_level = {
        frozenset([it]): cnt for it, cnt in item_counts.items() if cnt / n >= min_support
    }

    all_frequent = []
    for items, cnt in current_level.items():
        all_frequent.append(FrequentItemset(items, cnt / n, cnt))

    k = 2
    while current_level and k <= max_k:
        # Candidate generation: join itemsets from L_{k-1} that share k-2 items
        prev_itemsets = list(current_level.keys())
        candidates = set()
        for i in range(len(prev_itemsets)):
            for j in range(i + 1, len(prev_itemsets)):
                union = prev_itemsets[i] | prev_itemsets[j]
                if len(union) == k:
                    candidates.add(union)

        # Prune: a candidate can only survive if ALL its (k-1)-subsets were frequent
        # (the downward-closure / anti-monotonicity property)
        pruned = set()
        for cand in candidates:
            subsets_ok = all(frozenset(s) in current_level for s in combinations(cand, k - 1))
            if subsets_ok:
                pruned.add(cand)

        next_level = {}
        for cand in pruned:
            support, cnt = _support_of(cand, baskets)
            if support >= min_support:
                next_level[cand] = cnt
                all_frequent.append(FrequentItemset(cand, support, cnt))

        current_level = next_level
        k += 1

    return all_frequent


def generate_association_rules(baskets: List[set], min_support: float = 0.01,
                                 min_confidence: float = 0.2, min_lift: float = 1.0,
                                 max_k: int = 3) -> List[AssociationRule]:
    """Run Apriori, then derive A->B rules from every frequent itemset of size >= 2
    by splitting it into every non-trivial (antecedent, consequent) partition."""
    n = len(baskets)
    if n == 0:
        return []

    frequent = apriori_frequent_itemsets(baskets, min_support, max_k)
    support_lookup = {fi.items: fi.support for fi in frequent}

    rules = []
    for fi in frequent:
        items = fi.items
        if len(items) < 2:
            continue
        # Every way to split `items` into a non-empty antecedent + consequent
        for r in range(1, len(items)):
            for antecedent in combinations(items, r):
                antecedent = frozenset(antecedent)
                consequent = items - antecedent
                supp_a = support_lookup.get(antecedent)
                supp_b = support_lookup.get(consequent)
                if not supp_a or not supp_b:
                    continue
                supp_ab = fi.support
                confidence = supp_ab / supp_a
                lift = supp_ab / (supp_a * supp_b)
                denom = (1 - confidence)
                conviction = float("inf") if denom == 0 else (1 - supp_b) / denom

                if confidence >= min_confidence and lift >= min_lift:
                    rules.append(AssociationRule(
                        antecedent=antecedent, consequent=consequent,
                        support=supp_ab, confidence=confidence,
                        lift=lift, conviction=conviction,
                    ))

    rules.sort(key=lambda r: (r.lift, r.confidence), reverse=True)
    return rules


if __name__ == "__main__":
    # Tiny worked example to sanity-check the math independent of the DB.
    sample_baskets = [
        {"Chairs", "Desks"}, {"Chairs", "Desks"}, {"Chairs", "Paper"},
        {"Paper", "Binders"}, {"Chairs", "Desks"}, {"Binders", "Paper"},
        {"Phones", "Headsets"}, {"Chairs"}, {"Desks"}, {"Paper"},
    ]
    rules = generate_association_rules(sample_baskets, min_support=0.1,
                                        min_confidence=0.3, min_lift=1.0)
    print(f"{len(rules)} rules found:")
    for r in rules:
        print(" ", r)
