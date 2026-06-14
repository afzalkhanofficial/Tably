# DECISIONS.md — Engineering Decision Log

Format: Decision | Options Considered | Choice | Why

## D1: Time-Scoped Membership
Options: (A) Static membership table, (B) GroupMember with joined_at + left_at
Choice: B
Why: Sam's requirement — "I moved in mid-April, why would March electricity affect 
my balance?" Static membership cannot answer this. left_at=NULL means current member.
Trade-off: Slightly more complex queries, but balance accuracy is non-negotiable.

## D2: Currency Storage
Options: (A) Convert on the fly at query time, (B) Store both original + INR
Choice: B
Why: Exchange rates change daily. If we fetch rates at query time, balances will 
fluctuate day to day even for settled expenses. Storing the rate used at import 
time makes balances deterministic and auditable.

## D3: Balance Calculation Location
Options: (A) Calculated in DB (SQL aggregation), (B) In Python service layer
Choice: B
Why: The time-scoped membership filter (join/leave dates) and debt simplification 
algorithm are complex logic that would produce unreadable SQL. Python is more 
testable and traceable for the live interview.

## D4: Anomaly Resolution Policy
Options: (A) Crash on error, (B) Silent skip, (C) Surface + require approval
Choice: C
Why: The assignment explicitly says "A crashed import and a silent guess are both 
failing answers." Each anomaly has its own policy based on whether auto-resolution 
is safe (rounding, name matching) or financially ambiguous (duplicate amounts, 
missing payers).

## D5: Percentage Normalization
Options: (A) Auto-scale to 100% silently, (B) Block and require user correction
Choice: B
Why: Pizza Friday sums to 110%. Auto-scaling would change everyone's share. The 
"correct" fix is ambiguous — Meera might have meant 10%, not 20%. User must decide.
Offer scale-to-100 as a button option, not the default.

## D6: Negative Amounts
Options: (A) Flag as error, (B) Treat as refund/credit
Choice: B
Why: Row 26 has a clear note "one slot got cancelled." Negative expenses exist in 
real accounting. The split_with on the refund row matches the original expense — 
treating it as a credit distributed among the same people is correct.

## D7: Debt Simplification
Options: (A) Show raw pairwise balances, (B) Minimum-transaction settlement plan
Choice: B (with A also available as the Balances tab)
Why: Aisha's requirement: "one number per person." Without simplification, 
a 5-person group could have 10 bilateral debts. Greedy algorithm reduces this 
to 4 transactions maximum. Raw balances still shown in the Balances tab for 
Rohan's audit trail requirement.

## D8: Auth Strategy
Options: (A) Session cookies, (B) JWT tokens
Choice: B (JWT)
Why: React SPA calling a Django API is a cross-origin setup. JWT works 
naturally — no CSRF complexity. 8-hour access token with 7-day refresh balances 
security and UX.

## D9: Production Database Hosting
Options: (A) Render's managed free PostgreSQL, (B) Supabase free PostgreSQL,
(C) Neon.tech free PostgreSQL
Choice: B (Supabase)
Why: Render's free Postgres is deleted entirely after 30 days, risking the 
deployed app breaking before live evaluation. Supabase's free tier only 
pauses compute after 7 days of inactivity (data preserved, un-pauses on 
first request) — safer for a graded deliverable. Supabase also provides a 
Table Editor useful during the live session. Trade-off: Supabase's free 
connection is pooled (Supavisor, port 6543), so DB_CONN_MAX_AGE must be 0 
in production — Django can't hold persistent connections through a 
transaction-mode pooler.

---

## Free Tier Considerations

### Render Cold Starts
Render's free web services spin down automatically after 15 minutes of inactivity. When a request hits the service after it has idled, Render initiates a container cold start which takes approximately 30-50 seconds to complete. To maintain service readiness, a third-party keep-alive pinger (e.g. cron-job.org or UptimeRobot) can be configured to hit the backend `/api/health/` endpoint every 10 minutes.

### Supabase Inactivity Pauses
Supabase free tier databases pause their compute instance after 7 days of zero incoming connection traffic. Pausing does not delete database records or schema; rather, it suspends active compute. The database can be resumed either by navigating to the Supabase console dashboard or by sending a web request to the backend service which attempts to connect to the database (initiating a wake-up process taking 1-2 minutes).

### Connection Pooling
Using the pooled connection string on port 6543 requires database connection persistence (`DB_CONN_MAX_AGE`) to be set to `0`. If you upgrade or migrate to a direct database connection (port 5432) or a dedicated database cluster, `DB_CONN_MAX_AGE` should be set to a positive integer (e.g. `600` seconds) to reuse socket connections and optimize performance.

