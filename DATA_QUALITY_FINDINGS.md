# Data Quality & Normalization Opportunities

A deep-dive into what's weird about the values and strings in the dataset — and what rules an input layer (or ETL pipeline) should enforce.

## 1. Postal Codes — Leading Zeros Were Eaten (429 rows)

**Problem:** US ZIP codes are 5 digits, but 429 rows store only 4 digits because Excel silently stripped the leading zero.

| Stored | Actually |
|--------|----------|
| 6824 | 06824 (Fairfield, CT) |
| 7090 | 07090 (Westfield, NJ) |
| 7960 | 07960 (Morristown, NJ) |
| 1852 | 01852 (Lowell, MA) |

**Fix:** An input filter should pad ZIP codes to 5 digits and validate against a USPS dataset. Any 4-digit ZIP is automatically wrong.

## 2. Invisible Characters in Product Names — \xa0 (220 rows)

**Problem:** 220 product names contain non-breaking space characters (`\xa0`) that look like regular spaces to humans but break string matching, searching, and deduplication.

```
'Konftel 250 Conference\xa0phone\xa0- Charcoal black'
'Imation\xa08GB Mini TravelDrive USB 2.0\xa0Flash Drive'
```

**Fix:** Strip/replace all non-ASCII whitespace variants at input. Only ASCII 0x20 should be allowed as a space.

## 3. Double Spaces in Product Names (31 rows)

**Problem:** "EZD  Binder" (two spaces), "Tyvek  Top-Opening Peel & Seel  Envelopes". Causes issues in lookups and concatenation.

**Fix:** Collapse multiple spaces into one on entry.

## 4. Product ID ↔ Name Mapping Broken (32 Product IDs)

**Problem:** The same `Product ID` maps to completely different product names — this is a serious data integrity failure.

```
FUR-BO-10002213 → "DMI Eclipse Executive Suite Bookcases"
                → "Sauder Forest Hills Library, Woodland Oak Finish"

TEC-MA-10001148 → "Swingline SM12-08 MicroCut Jam Free Shredder"
                → "Okidata MB491 Multifunction Printer"
```

**Fix:** Product ID should be a unique key in a separate Products table. The ID-to-name mapping must be immutable after creation. The input layer should reject any attempt to reuse an existing Product ID with a different name.

## 5. Customer ID Case Inconsistency (43 rows)

**Problem:** Three Customer IDs use lowercase letters while every other ID is uppercase.

```
Dp-13240  (29 rows)
Co-12640  ( 8 rows)
Dl-13600  ( 6 rows)
```

**Fix:** Normalize to uppercase in the input layer. Better yet, auto-generate IDs so humans never type them.

## 6. Xerox Product Names Are Meaningless Codes (844 rows)

**Problem:** The vast majority of Xerox product entries look like "Xerox 2", "Xerox 22", "Xerox 1916", "Xerox 1881" — these are opaque model numbers that don't describe the product. Worse, they're easy to mistype (swap two digits and you get a different "product").

**Fix:** Product catalog should use manufacturer SKUs or full descriptions. Free-text entry of "Xerox 2" should be replaced by a dropdown from the catalog.

## 7. "Same Day" Shipping Took 1+ Day (24 rows)

**Problem:** 24 orders marked with `Ship Mode = Same Day` shipped the next day (1-day gap). Either the shipping mode was wrong or the date was wrong.

**Fix:** Add a business rule: if `Ship Mode = Same Day`, then `Ship Date - Order Date` must be 0. Reject or flag entries that violate this.

## 8. Sales Under $1 (8 rows)

**Problem:** Sales values like $0.44, $0.56, $0.84 for binders and hole punches. These are either partial/discount entries or data entry errors.

**Fix:** Set a minimum transaction threshold or force a separate `Discount` / `Quantity` field so tiny amounts are explainable.

## 9. 55 Cities Map to Multiple States

**Problem:** City names are ambiguous without context.

```
"Arlington" → VA (22204) or TX (76017)
"Auburn"    → NY (13021), WA (98002), AL (36830)
"Franklin"  → TN (37064), MA (02038), WI (53132), ...
```

**Fix:** City alone is not a reliable identifier. Input should require City + State (or City + ZIP) as a composite, perhaps validated against a geocoding API. A normalized Locations table with unique City/State/ZIP combinations would prevent ambiguity.

## 10. Only One Country, But Two Order ID Prefixes (9,800 rows)

**Problem:** Every row says `Country = United States`, yet Order IDs use both `CA-` and `US-` prefixes. If `CA-` originally meant Canada, that's stale logic. If it never did, the prefix is noise.

**Fix:** Either add a real Country column with values, or drop the redundant column and keep everything consistent.

## 11. 11 Missing Postal Codes

**Problem:** 11 rows have no ZIP code — but they have City and State. For logistics reporting, missing ZIPs are a blocker.

**Fix:** Make Postal Code a required field, or auto-fill it from a City/State lookup table on entry.

---

## Summary: What an Input Filter Should Do

| Rule | Severity | Count Affected |
|------|----------|---------------|
| Auto-pad + validate ZIP codes to 5 digits | High | 429 |
| Reject invisible Unicode whitespace (\xa0, etc.) | High | 220 |
| Collapse multiple spaces inside strings | Medium | 31 |
| Normalize Customer IDs to uppercase | Medium | 43 |
| Enforce unique Product ID ↔ Name mapping | Critical | 32 Product IDs |
| Validate Ship Mode vs Ship Date consistency | Medium | 24 |
| Require City + State (never City alone) | High | 55 ambiguous cities |
| Replace free-text product names with catalog dropdown | Medium | 844 Xerox entries |
| Require Postal Code (non-null) | High | 11 |

A proper normalized schema would prevent most of these at the database level (unique constraints, check constraints, FK references). The flat-file approach lets all of them through silently.
