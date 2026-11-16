# Query performance notes

Environment: PostgreSQL 16 in Docker Desktop on Windows, default configuration,
dataset loaded as described in the README (about 1.45 million rows across nine
tables, of which 1 million are geolocation). Timings are the median of several
`EXPLAIN (ANALYZE)` runs on a warm cache. At this data size every query
finishes in under a second, so these notes are about reading plans and
verifying index usage, and the honest summary is that indexes change little
here.

## Timings (median of 3 runs)

| Query | Median time |
|---|---|
| 01 monthly revenue trend | 217 ms |
| 02 cohort retention | 772 ms |
| 03 RFM segmentation | 371 ms |
| 04 rolling revenue | 220 ms |
| 05 top categories | 329 ms |
| 06 delivery delay vs reviews | 607 ms |
| 07 seller concentration | 233 ms |

The two heaviest queries, 02 and 06, were examined with
`EXPLAIN (ANALYZE, BUFFERS)`.

## Query 02, cohort retention (~800 ms)

What the plan shows:

- The `order_revenue` view is expanded three times (the `bounds`,
  `first_purchase`, and `activity` CTEs each reference it), so the
  orders-items-customers join pipeline runs three times. That triple
  evaluation, each pass hash-joining and hash-aggregating about 96,000 rows,
  is where nearly all the time goes.
- `idx_orders_purchase_ts` is used (Bitmap Index Scan) for the window filter.
  The filter keeps 96,211 of 99,441 orders, so a sequential scan would cost
  about the same. The planner picks the index partly because the window bounds
  come from a CROSS JOIN against the one-row `analysis_window` table, which
  hides the constants and makes it estimate 10,728 returned rows instead of
  the actual 96,211.
- Dropping `idx_customers_unique_id` and `idx_orders_status` changed the
  median from 730 ms to 719 ms, which is within run-to-run noise. Neither
  index appears in this plan. They are kept because they document intent and
  cost nothing to maintain at this size, and the status index is not useful to
  the planner anyway (97 percent of orders are 'delivered').

A materialized `order_revenue` would remove the triple evaluation. It was left
as a plain view because total runtime is under a second and a view cannot get
stale.

## Query 06, delivery delay vs reviews (~600 ms)

What the plan shows:

- The `order_reviews_clean` view (ROW_NUMBER over order_id) is computed with
  an Index Scan on `idx_order_reviews_order_id` followed by an Incremental
  Sort, so the partition step does not need a full sort of the reviews table.
- The final join back to `orders` for the delivery dates uses `orders_pkey`
  (95,568 index lookups).

Index effect, measured by dropping and recreating the index (median of 5 runs
each):

| Plan | Median time |
|---|---|
| with `idx_order_reviews_order_id` | 582 ms |
| without it (full external sort instead) | 656 ms |

The index helps, by roughly 13 percent. That is a real but small effect, which
is the expected result at 99,224 review rows: the table fits in memory and a
full sort is cheap.

## Summary

At this data size, most of the indexes serve as documentation of access paths
and change no timings. The one measurable win is the reviews index used by the
one-review-per-order deduplication (about 13 percent on query 06). The
timestamp index on orders is chosen by the planner but saves little, because
the analysis window keeps 96 percent of the table. If the data were 100x
larger, the same plans show where the pain would start: the repeated expansion
of `order_revenue` in query 02 would be the first thing to materialize.
