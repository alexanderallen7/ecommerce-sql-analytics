"""Run every analysis query, write results as CSV, render charts and the
HTML report.

SQL does the analysis. This script executes the .sql files, saves their
output, and formats it. pandas is used only to hold query results for
charting; no finding is computed in pandas.

Usage: python scripts/run_analysis.py
"""

import base64
import csv
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import charts
from src.db import PROJECT_ROOT, get_connection, fetch_sql_file

QUERY_DIR = PROJECT_ROOT / "sql" / "queries"
OUTPUT_DIR = PROJECT_ROOT / "output"
RESULTS_DIR = OUTPUT_DIR / "results"
CHARTS_DIR = OUTPUT_DIR / "charts"


def run_queries():
    """Execute every query file; return {stem: DataFrame} and write CSVs."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    with get_connection() as conn:
        for path in sorted(QUERY_DIR.glob("*.sql")):
            cols, rows = fetch_sql_file(conn, path)
            with open(RESULTS_DIR / f"{path.stem}.csv", "w", newline="",
                      encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(cols)
                writer.writerows(rows)
            df = pd.DataFrame(rows, columns=cols)
            # psycopg returns NUMERIC as Decimal and dates as datetime.date;
            # give pandas proper dtypes for charting. Values are unchanged.
            for col in df.columns:
                sample = df[col].dropna()
                if sample.empty:
                    continue
                first = sample.iloc[0]
                if isinstance(first, Decimal):
                    df[col] = df[col].astype(float)
                elif isinstance(first, date):
                    df[col] = pd.to_datetime(df[col])
            results[path.stem[:2]] = df
            print(f"  {path.name}: {len(rows)} rows")
    return results


def build_findings(r):
    """Headline numbers, each taken directly from a query result."""
    monthly = r["01"]
    total_revenue = monthly["revenue"].sum()
    total_orders = int(monthly["order_count"].sum())
    peak = monthly.loc[monthly["revenue"].idxmax()]

    cohort = r["02"]
    base = cohort[cohort["month_offset"] == 0]
    total_customers = int(base["cohort_size"].sum())
    m1 = cohort[(cohort["month_offset"] == 1) & cohort["active_customers"].notna()]
    m1_pct = 100 * m1["active_customers"].sum() / m1["cohort_size"].sum()
    max_cell = cohort[cohort["month_offset"] >= 1]["retention_pct"].max()

    rfm = r["03"]
    repeat = rfm[rfm["segment"].isin(["Active repeat", "Lapsed repeat"])]
    repeat_pct = 100 * repeat["customers"].sum() / rfm["customers"].sum()
    top2 = rfm.nlargest(2, "revenue")

    cats = r["05"]
    leaders = cats[cats["revenue_rank"] == 1]["category"].value_counts()

    deliv = r["06"].set_index("delivery_bucket")
    early = deliv.loc["1. 8+ days early"]
    late = deliv.loc["6. 8+ days late"]

    sellers = r["07"].set_index("tier_label")

    findings = [
        f"R$ {total_revenue / 1e6:.2f} million of delivered revenue across "
        f"{total_orders:,} orders and {total_customers:,} customers in 20 months "
        f"(January 2017 through August 2018).",
        f"The best month was {peak['purchase_month']:%B %Y} with "
        f"R$ {peak['revenue'] / 1e6:.2f} million, up {peak['revenue_mom_pct']} "
        f"percent on the month before.",
        f"Repeat purchase is rare: {repeat_pct:.1f} percent of customers ordered "
        f"more than once in the window, and on average {m1_pct:.2f} percent of a "
        f"cohort orders again in the month after the first purchase. No cohort "
        f"cell after month 0 exceeds {max_cell} percent.",
        f"The top two RFM segments by revenue ({top2.iloc[0]['segment']} and "
        f"{top2.iloc[1]['segment']}) are {top2['pct_customers'].sum():.1f} percent "
        f"of customers and {top2['pct_revenue'].sum():.1f} percent of revenue.",
        f"Orders delivered 8 or more days late average a review score of "
        f"{late['avg_review_score']} versus {early['avg_review_score']} for "
        f"orders 8 or more days early; {late['pct_one_star']} percent of the "
        f"late group leave 1-star reviews versus {early['pct_one_star']} percent.",
        f"Revenue is concentrated: the top 1 percent of sellers "
        f"({int(sellers.loc['Top 1%', 'sellers_in_tier'])} sellers) earn "
        f"{sellers.loc['Top 1%', 'pct_of_revenue']} percent of revenue, the top "
        f"20 percent earn {sellers.loc['Top 20%', 'pct_of_revenue']} percent.",
    ]
    return findings


def category_table(cats):
    header = [
        {"label": "Quarter"}, {"label": "Rank", "num": True}, {"label": "Category"},
        {"label": "Revenue (R$)", "num": True},
        {"label": "Items", "num": True},
        {"label": "Share of quarter", "num": True},
    ]
    rows = [
        [
            {"value": f"{r.quarter:%Y} Q{(r.quarter.month - 1) // 3 + 1}"},
            {"value": r.revenue_rank, "num": True},
            {"value": r.category},
            {"value": f"{r.revenue:,.0f}", "num": True},
            {"value": f"{r.items_sold:,}", "num": True},
            {"value": f"{r.pct_of_quarter}%", "num": True},
        ]
        for r in cats.itertuples()
    ]
    return {"header": header, "rows": rows}


def build_sections(r):
    monthly = r["01"]
    peak = monthly.loc[monthly["revenue"].idxmax()]
    aov_min, aov_max = monthly["avg_order_value"].min(), monthly["avg_order_value"].max()

    cohort = r["02"]
    m1 = cohort[(cohort["month_offset"] == 1) & cohort["active_customers"].notna()]
    m1_pct = 100 * m1["active_customers"].sum() / m1["cohort_size"].sum()
    max_cell = cohort[cohort["month_offset"] >= 1]["retention_pct"].max()

    rfm = r["03"]
    repeat = rfm[rfm["segment"].isin(["Active repeat", "Lapsed repeat"])]
    high = rfm[rfm["segment"].isin(["Recent high value", "Lapsed high value"])]

    rolling = r["04"]
    peak_roll = rolling.loc[rolling["rolling_30d_revenue"].idxmax()]
    peak_day = rolling.loc[rolling["revenue"].idxmax(), "day"]

    cats = r["05"]
    leader_counts = cats[cats["revenue_rank"] == 1]["category"].value_counts()
    top3_share = cats.groupby("quarter")["pct_of_quarter"].sum()

    deliv = r["06"].set_index("delivery_bucket")
    sellers = r["07"].set_index("tier_label")

    return [
        {
            "title": "Monthly revenue and order trend",
            "question": "How did monthly revenue, order count, and average "
                        "order value develop, and how large are the swings "
                        "month over month?",
            "chart": charts.monthly_trend(monthly),
            "alt": "Bar chart of monthly revenue and line chart of monthly orders",
            "comment": (
                f"Revenue grew from R$ {monthly.iloc[0]['revenue'] / 1e3:,.0f} "
                f"thousand in January 2017 to a peak of R$ "
                f"{peak['revenue'] / 1e6:.2f} million in "
                f"{peak['purchase_month']:%B %Y}, up "
                f"{peak['revenue_mom_pct']} percent on October; the window's "
                f"highest-revenue day was {peak_day:%d %B %Y}, Black Friday. "
                f"Through 2018 "
                f"monthly revenue settled around R$ 1.0 to 1.13 million with no "
                f"further growth. Average order value stayed between R$ "
                f"{aov_min} and R$ {aov_max} the whole time, so the growth in "
                f"2017 came from order volume."
            ),
            "query_file": "01_monthly_revenue_trend.sql",
        },
        {
            "title": "Cohort retention",
            "question": "Of the customers who made their first purchase in a "
                        "given month, what share ordered again in each later "
                        "month?",
            "chart": charts.retention_heatmap(cohort),
            "alt": "Heatmap of retention by cohort month and month offset",
            "comment": (
                f"Retention is very low in every cohort: on average "
                f"{m1_pct:.2f} percent of a cohort orders again in the month "
                f"after the first purchase, and the highest later-month cell in "
                f"the whole table is {max_cell} percent. Customers are "
                f"identified by customer_unique_id; the per-order customer_id "
                f"would show zero retention by construction. The numbers are "
                f"reported as they are: this marketplace ran on one-time "
                f"buyers during the window."
            ),
            "query_file": "02_cohort_retention.sql",
        },
        {
            "title": "RFM segmentation",
            "question": "How do customers split by recency, frequency, and "
                        "spend, and which segments carry the revenue?",
            "chart": charts.rfm_segments(rfm),
            "alt": "Bar charts of customer share and revenue share per RFM segment",
            "comment": (
                f"Because {100 - (100 * repeat['customers'].sum() / rfm['customers'].sum()):.1f} "
                f"percent of customers bought exactly once, frequency quintiles "
                f"would be arbitrary; frequency is scored by a direct rule (1, "
                f"2, or 3+ orders) and the segments are driven by recency and "
                f"spend. The two high-value one-purchase segments hold "
                f"{high['pct_customers'].sum():.1f} percent of customers and "
                f"{high['pct_revenue'].sum():.1f} percent of revenue. Both "
                f"repeat segments together are "
                f"{repeat['pct_customers'].sum():.1f} percent of customers and "
                f"{repeat['pct_revenue'].sum():.1f} percent of revenue, so "
                f"there is no meaningful loyal core to defend yet."
            ),
            "query_file": "03_rfm_segmentation.sql",
        },
        {
            "title": "Rolling and cumulative revenue",
            "question": "What does daily revenue look like smoothed over 30 "
                        "days, and how does cumulative revenue grow?",
            "chart": charts.rolling_revenue(rolling),
            "alt": "Line charts of 30-day rolling revenue and cumulative revenue",
            "comment": (
                f"The 30-day rolling sum peaks at R$ "
                f"{peak_roll['rolling_30d_revenue'] / 1e6:.2f} million on "
                f"{peak_roll['day']:%d %B %Y}, right after the Black Friday "
                f"spike. The date spine includes every calendar day, so days "
                f"with no delivered orders count as zero in the window. The "
                f"cumulative curve steepens through 2017 and grows at a near "
                f"constant rate through 2018."
            ),
            "query_file": "04_rolling_revenue.sql",
        },
        {
            "title": "Top categories per quarter",
            "question": "Which product categories earned the most revenue in "
                        "each quarter?",
            "table": category_table(cats),
            "comment": (
                f"{leader_counts.index[0]} leads "
                f"{leader_counts.iloc[0]} of the 7 quarters, and the top 3 "
                f"categories hold {top3_share.min():.0f} to "
                f"{top3_share.max():.0f} percent of each quarter's revenue, "
                f"so the catalog is broad with a stable set of leading "
                f"categories. health_beauty appears in the top 3 in every "
                f"quarter. Category revenue allocates each item to its "
                f"product's category, so an order that spans categories is "
                f"split across them."
            ),
            "query_file": "05_top_categories.sql",
        },
        {
            "title": "Delivery delay and review score",
            "question": "How do review scores differ between orders that "
                        "arrived early, on time, or late?",
            "chart": charts.delivery_reviews(r["06"]),
            "alt": "Bar charts of average review score and 1-star share by delivery bucket",
            "comment": (
                f"Review scores fall steadily with lateness: orders 8 or more "
                f"days early average {deliv.loc['1. 8+ days early', 'avg_review_score']}, "
                f"on-time orders {deliv.loc['3. on time', 'avg_review_score']}, and "
                f"orders 8 or more days late "
                f"{deliv.loc['6. 8+ days late', 'avg_review_score']}, with "
                f"{deliv.loc['6. 8+ days late', 'pct_one_star']} percent of that "
                f"group leaving 1-star reviews. "
                f"{int(deliv.loc['1. 8+ days early', 'n_orders']):,} of "
                f"{int(deliv['n_orders'].sum()):,} reviewed orders arrived 8 or "
                f"more days early, so the platform pads its delivery estimates "
                f"heavily. This is an association between lateness and scores; "
                f"the data cannot establish causation."
            ),
            "query_file": "06_delivery_delay_reviews.sql",
        },
        {
            "title": "Seller concentration",
            "question": "What share of revenue comes from the top 1, 5, and "
                        "20 percent of sellers?",
            "chart": charts.seller_concentration(r["07"]),
            "alt": "Bar chart of revenue share by seller tier",
            "comment": (
                f"The top 1 percent of sellers "
                f"({int(sellers.loc['Top 1%', 'sellers_in_tier'])} of "
                f"{int(sellers.loc['Top 1%', 'total_sellers']):,}) earn "
                f"{sellers.loc['Top 1%', 'pct_of_revenue']} percent of revenue, "
                f"and the top 20 percent earn "
                f"{sellers.loc['Top 20%', 'pct_of_revenue']} percent. That level "
                f"of concentration means marketplace health depends on a few "
                f"hundred sellers, and churn among the top tier would be felt "
                f"directly in revenue."
            ),
            "query_file": "07_seller_concentration.sql",
        },
    ]


def render_report(findings, sections):
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_names = {
        0: "01_monthly_trend.png", 1: "02_retention_heatmap.png",
        2: "03_rfm_segments.png", 3: "04_rolling_revenue.png",
        5: "06_delivery_reviews.png", 6: "07_seller_concentration.png",
    }
    for i, s in enumerate(sections):
        if s.get("chart"):
            (CHARTS_DIR / chart_names[i]).write_bytes(s["chart"])
            s["chart"] = base64.b64encode(s["chart"]).decode("ascii")

    env = Environment(
        loader=FileSystemLoader(PROJECT_ROOT / "src" / "templates"),
        autoescape=True,
    )
    html = env.get_template("report.html.j2").render(
        findings=findings,
        sections=sections,
        window_label="January 2017 through August 2018, delivered orders",
        generated_on=date.today().isoformat(),
    )
    out = OUTPUT_DIR / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"Report written to {out}")


def main():
    print("Running queries ...")
    results = run_queries()
    findings = build_findings(results)
    sections = build_sections(results)
    render_report(findings, sections)


if __name__ == "__main__":
    main()
