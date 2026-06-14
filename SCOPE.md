# SCOPE.md — Anomaly Log & Database Schema

## Part 1: CSV Anomaly Log

| # | CSV Row | Anomaly Type | Description | Policy Chosen | Rationale |
|---|---|---|---|---|---|
| 1 | 6 | EXACT_DUPLICATE | Row 6 is identical to Row 5 (Marina Bites dinner — same date, payer, amount, split) | Flag for user approval. Default: skip Row 6, keep Row 5. | Cannot silently delete — Meera's request. But clearly duplicate. |
| 2 | 7 | AMOUNT_FORMAT | "1,200" contains comma, not parseable as number | Auto-fix: strip comma → 1200. Log change. | Unambiguous mechanical fix. Safe to auto-correct. |
| 3 | 9,11,27 | NAME_FUZZY_MATCH | "priya"→Priya, "Priya S"→Priya, "rohan "→Rohan | Auto-fix: resolve to canonical name if similarity ≥80%. Log original. | Strong signal of same person. 80% threshold avoids false positives. |
| 4 | 13 | MISSING_PAID_BY | House cleaning supplies — payer blank | Block: import as draft, require user to assign payer before settlement | Cannot guess payer — would silently corrupt balances |
| 5 | 14,38 | SETTLEMENT_PATTERN | "Rohan paid Aisha back" and "Sam deposit share" are payments, not expenses | Auto-convert: create Settlement record, not Expense | Settlement keywords in description are unambiguous |
| 6 | 15 | PERCENTAGE_SUM_ERROR | Pizza Friday: 30+30+30+20 = 110%, not 100% | Block: require user to correct. Offer "scale to 100%" as option. | Two valid fixes (scale vs reassign) have different financial outcomes |
| 7 | 20,21,23,26 | FOREIGN_CURRENCY | USD amounts — fetched historical INR rate from Frankfurter API | Auto-fix: convert + store original currency + rate used + rate date | Priya's explicit requirement. Rate date matches expense date. |
| 8 | 23 | UNKNOWN_MEMBER | "Dev's friend Kabir" not in member list | Block: require user to choose add-as-guest or absorb-share | Cannot infer correct action — financial impact differs |
| 9 | 24,25 | CONFLICTING_DUPLICATE | Two Thalassa dinner entries, same date, different amounts, different payers | Block: require user to pick one or confirm both | Financial outcome differs by ₹50. Cannot guess. |
| 10 | 26 | NEGATIVE_AMOUNT | Parasailing refund -USD 30 | Auto-fix: treat as refund, split credit proportionally among split_with | Refunds are valid accounting entries. Negative = credit. |
| 11 | 27 | NONSTANDARD_DATE | "Mar-14" not in expected date formats | Auto-fix: parse with dateutil → 2026-03-14. Log inferred date. | Single valid interpretation given context (2026 trip). |
| 12 | 28 | MISSING_CURRENCY | Groceries DMart — currency cell empty | Auto-fix + confirm: default to INR, surface to user for confirmation | All other domestic expenses are INR. Strong default. |
| 13 | 31 | ZERO_AMOUNT | Swiggy ₹0 — notes say "counted twice earlier" | Skip: do not import. Log reason. | ₹0 creates split records with no financial effect. Note confirms it's a placeholder. |
| 14 | 34 | AMBIGUOUS_DATE | "04-05-2026" valid as April 5 or May 4 | Block: require user to pick interpretation | Context is unclear — notes only say format is a mess |
| 15 | 36 | MEMBER_POST_DEPARTURE | Meera in April groceries after she left 2026-03-28 | Auto-fix + confirm: remove Meera, recalculate shares, surface to user | Sam's requirement: join date must be respected. Meera's: show change before applying. |
| 16 | 42 | SPLIT_TYPE_CONFLICT | split_type=equal but share details provided (all equal shares) | Auto-fix: use equal split, ignore details, log | Both interpretations produce same result (all shares are 1:1:1:1). |
| 17 | 10 | DECIMAL_PRECISION | ₹899.995 has 3 decimal places — INR has 2 | Auto-fix: round to ₹900.00 (ROUND_HALF_UP). Log. | Standard financial rounding. No ambiguity. |

## Part 2: Database Schema

Our relational schema consists of 10 tables detailed below:

### 1. `users` Table
Stores custom user profiles using email as the unique login field.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `email` (VarChar(254)): Unique, index. Log-in identifier.
    *   `name` (VarChar(150)): User's display name.
    *   `avatar_color` (VarChar(7)): Hex color for UI avatars (default: `#6366F1`).
    *   `password` (VarChar(128)): Hashed password.
    *   `is_superuser` (Boolean): Admin status flag.
    *   `is_staff` (Boolean): Dashboard access flag.
    *   `is_active` (Boolean): Soft-delete flag for accounts.
    *   `date_joined` (DateTimeTz): Profile registration timestamp.
    *   `last_login` (DateTimeTz): Last authenticated timestamp.
*   **Indexes**:
    *   `users_email_idx` on `email` (Unique).

### 2. `groups` Table
Tracks shared flat groups.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `name` (VarChar(200)): Group identifier name.
    *   `description` (Text): Short description of group members/purposes.
    *   `created_by_id` (BigInt): Foreign Key referencing `users(id)`, nullable.
    *   `created_at` (DateTimeTz): Creation timestamp.

### 3. `group_members` Table
Stores time-scoped group membership.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `group_id` (BigInt): Foreign Key referencing `groups(id)`.
    *   `user_id` (BigInt): Foreign Key referencing `users(id)`.
    *   `joined_at` (Date): Membership entry date.
    *   `left_at` (Date): Departure date, nullable.
*   **Constraints & Indexes**:
    *   `group_members_group_user_joined_unique` Unique together on `(group_id, user_id, joined_at)`.

### 4. `expenses` Table
Tracks expenses made by users.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `group_id` (BigInt): Foreign Key referencing `groups(id)`.
    *   `description` (VarChar(500)): Expense title.
    *   `total_amount` (Decimal(12,2)): Original transaction amount.
    *   `currency` (VarChar(3)): Choice of original currency (INR, USD, EUR, GBP).
    *   `amount_inr` (Decimal(12,2)): Amount converted to INR.
    *   `exchange_rate_used` (Decimal(12,6)): Exchange rate multiplier, nullable.
    *   `exchange_rate_date` (Date): Date of exchange rate lookup, nullable.
    *   `paid_by_id` (BigInt): Foreign Key referencing `users(id)`, nullable.
    *   `expense_date` (Date): Date of transaction.
    *   `split_type` (VarChar(20)): Split model (equal, unequal, percentage, share).
    *   `is_settlement` (Boolean): True if it represents a repayment settlement.
    *   `is_refund` (Boolean): True for refunds (negative values).
    *   `is_deleted` (Boolean): Soft delete flag.
    *   `notes` (Text): Additional comments.
    *   `import_row_ref` (Integer): Row line in CSV source, nullable.
    *   `import_session_id` (BigInt): Foreign Key referencing `import_sessions(id)`, nullable.
    *   `created_by_id` (BigInt): Foreign Key referencing `users(id)`, nullable.
    *   `created_at` (DateTimeTz): Insertion timestamp.
    *   `updated_at` (DateTimeTz): Modification timestamp.
*   **Indexes**:
    *   `expenses_group_date_idx` on `(group_id, expense_date)`.
    *   `expenses_group_deleted_idx` on `(group_id, is_deleted)`.
    *   `expenses_paid_by_idx` on `(paid_by_id)`.

### 5. `expense_splits` Table
Links user shares to individual expenses in INR.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `expense_id` (BigInt): Foreign Key referencing `expenses(id)`.
    *   `user_id` (BigInt): Foreign Key referencing `users(id)`.
    *   `amount_owed` (Decimal(12,2)): Amount owed in INR.
*   **Constraints**:
    *   `expense_splits_expense_user_unique` Unique together on `(expense_id, user_id)`.

### 6. `settlements` Table
Tracks direct settlements.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `group_id` (BigInt): Foreign Key referencing `groups(id)`.
    *   `paid_by_id` (BigInt): Foreign Key referencing `users(id)`.
    *   `paid_to_id` (BigInt): Foreign Key referencing `users(id)`.
    *   `amount` (Decimal(12,2)): Raw paid amount.
    *   `currency` (VarChar(3)): Repayment currency.
    *   `amount_inr` (Decimal(12,2)): Repayment converted to INR.
    *   `notes` (Text): Transaction details.
    *   `settled_at` (DateTimeTz): Execution date.
    *   `import_row_ref` (Integer): Row line in CSV source, nullable.
    *   `created_by_id` (BigInt): Foreign Key referencing `users(id)`, nullable.

### 7. `import_sessions` Table
Maintains CSV import sessions.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `filename` (VarChar(255)): Uploaded CSV file name.
    *   `group_id` (BigInt): Foreign Key referencing `groups(id)`.
    *   `imported_by_id` (BigInt): Foreign Key referencing `users(id)`.
    *   `imported_at` (DateTimeTz): Import initialization timestamp.
    *   `status` (VarChar(20)): Processing state (processing, pending_review, complete, failed).
    *   `total_rows` (Integer): Total parsed rows.
    *   `auto_imported_count` (Integer): Total rows imported clean.
    *   `auto_fixed_count` (Integer): Total rows auto-fixed.
    *   `pending_review_count` (Integer): Total rows needing review.
    *   `skipped_count` (Integer): Total skipped rows.

### 8. `import_anomalies` Table
Tracks import anomalies.
*   **Columns**:
    *   `id` (BigInt): Primary Key, auto-increment.
    *   `session_id` (BigInt): Foreign Key referencing `import_sessions(id)`.
    *   `row_number` (Integer): Row number in the CSV.
    *   `anomaly_type` (VarChar(50)): Type identifier for the anomaly.
    *   `description` (Text): Human explanation.
    *   `raw_row_data` (JSON): Copy of the original CSV row columns.
    *   `suggested_fix` (JSON): Recommended parsed solution variables, nullable.
    *   `action_taken` (VarChar(30)): Action log (AUTO_FIXED, PENDING_USER, etc.).
    *   `requires_user_approval` (Boolean): True if user decision is mandatory.
    *   `resolved` (Boolean): True when user makes a decision.
    *   `resolution_choice` (VarChar(50)): Choice select ("keep", "skip", "set_value").
    *   `resolution_value` (JSON): Custom data override, nullable.
    *   `resolved_by_id` (BigInt): Foreign Key referencing `users(id)`, nullable.
    *   `resolved_at` (DateTimeTz): Completion date, nullable.

### 9. `django_session` Table
Django system session store.
*   **Columns**:
    *   `session_key` (VarChar(40)): Primary Key.
    *   `session_data` (Text): Encoded session dictionary.
    *   `expire_date` (DateTimeTz): Expiration timestamp.

### 10. `django_migrations` Table
Tracks active Django schema migration steps.
*   **Columns**:
    *   `id` (Integer): Primary Key, auto-increment.
    *   `app` (VarChar(255)): Name of the Django app.
    *   `name` (VarChar(255)): Name of the migration file.
    *   `applied` (DateTimeTz): Date applied.

---

## Part 3: Split Types Supported

| Type | Description | CSV Example | Calculation |
|---|---|---|---|
| equal | Same amount per person | February rent ÷ 4 | total_inr / count |
| unequal | Fixed INR per person | Birthday cake: Rohan ₹700, Priya ₹400, Meera ₹400 | Direct from split_details |
| percentage | % of total per person | Pizza Friday 30/30/30/10 | (pct/100) × total |
| share | Ratio-based | Scooter: Aisha 1, Rohan 2, Priya 1, Dev 2 | (shares/total_shares) × total |

---

## Part 4: Membership Timeline

*   **Aisha**: 2026-02-01 → present
*   **Rohan**: 2026-02-01 → present
*   **Priya**: 2026-02-01 → present
*   **Meera**: 2026-02-01 → 2026-03-28 (moved out)
*   **Sam**: 2026-04-08 → present (moved in mid-April)
*   **Dev**: Guest (User record only, no GroupMember record)
