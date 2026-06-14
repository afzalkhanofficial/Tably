# AI_USAGE.md

## Tools Used
- Claude (Anthropic, claude.ai)
- Used as: code generator, logic reviewer, documentation drafter

## Workflow
Every AI-generated output was:
1. Read line by line before running
2. Tested against a known expected output
3. Committed only after manual verification

## Three Cases Where Claude Was Wrong

### Case 1: Balance Calculator Ignored Time-Scoped Membership
Claude's initial get_group_balances() fetched ALL expense splits for the group 
and summed them without checking member join/leave dates.

How caught: Manually traced Sam's balance. Sam joined April 8. March electricity 
(Row 29) had Sam in the split. Claude's code gave Sam a -₹362.50 balance 
contribution from that row. Correct answer: ₹0 (Sam wasn't there).

Fix: Added is_active_on() method to GroupMember model and added date validation 
in the balance calculator before including any split.

### Case 2: Percentage Detector Auto-Normalized Silently
Claude's check_percentage_sum() returned AUTO_FIXED and divided each percentage 
by the sum to normalize to 100%. For Pizza Friday (sums to 110%), this would 
silently change Aisha's share from 30% to 27.27%.

How caught: Re-read the anomaly policy requirements. The assignment says 
"surface it to the user." Silent financial changes are exactly what Meera's 
request was about. Auto-normalization is a guess at who should pay less.

Fix: Changed action to PENDING_USER, requires_user_approval=True, and offered 
"scale_to_150" / "scale_to_100" as a button option the user explicitly clicks.

### Case 3: Duplicate Detector Used Exact String Match
Claude's _find_duplicates() compared description strings with == after lowercasing.
This found Marina Bites (exact match) but completely missed Thalassa dinner vs 
Dinner at Thalassa (word order different, fuzzy similarity 0.76).

How caught: Manually checked rows 24 and 25. Both show up as clean rows in 
Claude's version. Running the importer produced two Thalassa dinner expenses 
with different amounts — ₹2400 and ₹2450 — both committed to the database.

Fix: Added SequenceMatcher fuzzy comparison for same-date rows with threshold 
≥ 0.6 similarity. This catches word-order swaps and abbreviations.

## Key Prompts Used
- "Build a balance calculator that respects time-scoped group membership..."
- "Detect CSV anomalies and return AnomalyResult objects, never silently fix 
   financial ambiguities..."
- "Build the minimum-transaction debt settlement greedy algorithm..."
- "Generate unit tests that verify splits sum exactly to total..."
