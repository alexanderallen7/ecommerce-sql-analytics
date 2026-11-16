"""Chart rendering for the report.

All numbers plotted here come straight from the SQL query results handed in
by scripts/run_analysis.py. Nothing is computed here beyond reshaping.
"""

from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

# Palette (light surface).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
SEQ_STEPS = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]
# Ordinal ramp for a handful of ordered marks: no lighter than step 250.
ORDINAL = ["#86b6ef", "#5598e7", "#3987e5", "#256abf", "#1c5cab", "#104281"]
SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQ_STEPS)
UNOBSERVABLE = "#f0efec"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "Segoe UI",
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": BASELINE,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "font.size": 9,
        "figure.dpi": 150,
    }
)


def _fig_to_png_bytes(fig) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _style_axis(ax, y_grid_only=True):
    if y_grid_only:
        ax.grid(axis="y")
        ax.grid(False, axis="x")
    ax.tick_params(length=0)


def monthly_trend(df) -> bytes:
    """Two panels: monthly revenue bars, monthly order count line."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8.2, 5.2), sharex=True, gridspec_kw={"hspace": 0.35}
    )
    months = df["purchase_month"]
    ax1.bar(months, df["revenue"] / 1000, width=22, color=BLUE)
    ax1.set_title("Monthly revenue (R$ thousand)")
    ax2.plot(months, df["order_count"], color=BLUE, linewidth=2)
    ax2.scatter(months, df["order_count"], color=BLUE, s=12, zorder=3)
    ax2.set_title("Monthly delivered orders")
    for ax in (ax1, ax2):
        _style_axis(ax)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.margins(x=0.02)
    peak = df.loc[df["revenue"].idxmax()]
    ax1.annotate(
        f"R$ {peak['revenue'] / 1000:,.0f}k",
        (peak["purchase_month"], peak["revenue"] / 1000),
        textcoords="offset points", xytext=(0, 4),
        ha="center", fontsize=8, color=INK_2,
    )
    return _fig_to_png_bytes(fig)


def retention_heatmap(df) -> bytes:
    """Cohort month x month offset. Offset 0 (always 100 percent) is dropped;
    unobservable cells render gray, observed zeros render on the ramp."""
    data = df[df["month_offset"] >= 1]
    pivot = data.pivot(
        index="cohort_month", columns="month_offset", values="retention_pct"
    ).astype(float)
    sizes = (
        df[df["month_offset"] == 0]
        .set_index("cohort_month")["cohort_size"]
        .reindex(pivot.index)
    )
    vmax = float(np.nanmax(pivot.to_numpy()))

    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    cmap = SEQ_CMAP.copy()
    cmap.set_bad(UNOBSERVABLE)
    masked = np.ma.masked_invalid(pivot.to_numpy())
    im = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    ax.set_xticks(range(pivot.shape[1]), [str(c) for c in pivot.columns])
    ax.set_yticks(
        range(pivot.shape[0]),
        [f"{m:%b %Y}  (n={int(s):,})" for m, s in zip(pivot.index, sizes)],
    )
    ax.set_xlabel("Months since first purchase")
    ax.set_title("Share of cohort ordering again (%), by months since first purchase")
    ax.grid(False)
    ax.tick_params(length=0)
    # White hairline between cells.
    ax.set_xticks(np.arange(-0.5, pivot.shape[1]), minor=True)
    ax.set_yticks(np.arange(-0.5, pivot.shape[0]), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1.5)
    ax.tick_params(which="minor", length=0)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.ax.tick_params(length=0, labelsize=8)
    cbar.outline.set_visible(False)
    ax.text(
        0, 1.14, "Gray cells fall after August 2018 and cannot be observed.",
        transform=ax.transAxes, fontsize=8, color=MUTED,
    )
    return _fig_to_png_bytes(fig)


def rfm_segments(df) -> bytes:
    """Two panels: share of customers and share of revenue per segment."""
    d = df.sort_values("pct_revenue", ascending=True)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(8.6, 3.4), sharey=True, gridspec_kw={"wspace": 0.08}
    )
    y = np.arange(len(d))
    ax1.barh(y, d["pct_customers"], color=BLUE, height=0.62)
    ax1.set_title("Share of customers (%)")
    ax2.barh(y, d["pct_revenue"], color=BLUE, height=0.62)
    ax2.set_title("Share of revenue (%)")
    ax1.set_yticks(y, d["segment"])
    for ax, col in ((ax1, "pct_customers"), (ax2, "pct_revenue")):
        ax.grid(axis="x")
        ax.grid(False, axis="y")
        ax.tick_params(length=0)
        for yi, v in zip(y, d[col]):
            ax.text(float(v) + 0.5, yi, f"{v}", va="center", fontsize=8, color=INK_2)
        ax.set_xlim(0, max(float(d[col].max()) * 1.18, 10))
    return _fig_to_png_bytes(fig)


def rolling_revenue(df) -> bytes:
    """Two panels: 30-day rolling revenue, cumulative revenue."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8.2, 5.2), sharex=True, gridspec_kw={"hspace": 0.35}
    )
    days = df["day"]
    complete = df["rolling_window_complete"]
    ax1.plot(
        days[~complete], df["rolling_30d_revenue"][~complete] / 1000,
        color=MUTED, linewidth=1.4, linestyle=(0, (3, 2)),
    )
    ax1.plot(
        days[complete], df["rolling_30d_revenue"][complete] / 1000,
        color=BLUE, linewidth=2,
    )
    ax1.set_title("30-day rolling revenue (R$ thousand)")
    ax1.text(
        1.0, 1.06, "Dashed: first 29 days, where the window is still partial.",
        transform=ax1.transAxes, fontsize=8, color=MUTED, ha="right",
    )
    ax2.plot(days, df["cumulative_revenue"] / 1e6, color=BLUE, linewidth=2)
    ax2.set_title("Cumulative revenue (R$ million)")
    for ax in (ax1, ax2):
        _style_axis(ax)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.margins(x=0.02)
    return _fig_to_png_bytes(fig)


def delivery_reviews(df) -> bytes:
    """Two panels over the same delivery buckets: average score, 1-star share."""
    labels = [b.split(". ", 1)[1] for b in df["delivery_bucket"]]
    colors = ORDINAL[: len(df)]
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(8.6, 3.4), gridspec_kw={"wspace": 0.25}
    )
    x = np.arange(len(df))
    ax1.bar(x, df["avg_review_score"], color=colors, width=0.62)
    ax1.set_title("Average review score (1 to 5)")
    ax1.set_ylim(0, 5)
    ax2.bar(x, df["pct_one_star"], color=colors, width=0.62)
    ax2.set_title("Share of 1-star reviews (%)")
    for ax, col in ((ax1, "avg_review_score"), (ax2, "pct_one_star")):
        ax.set_xticks(x, labels, rotation=30, ha="right", fontsize=8)
        _style_axis(ax)
        for xi, v in zip(x, df[col]):
            ax.text(xi, float(v), f"{v}", ha="center", va="bottom",
                    fontsize=8, color=INK_2)
    return _fig_to_png_bytes(fig)


def seller_concentration(df) -> bytes:
    """Share of revenue captured by the top seller tiers."""
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    y = np.arange(len(df))
    ax.barh(y, df["pct_of_revenue"], color=ORDINAL[: len(df)], height=0.56)
    ax.set_yticks(
        y,
        [
            f"{t} ({int(n):,} of {int(tot):,} sellers)"
            for t, n, tot in zip(
                df["tier_label"], df["sellers_in_tier"], df["total_sellers"]
            )
        ],
    )
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_title("Share of revenue (%)")
    ax.grid(axis="x")
    ax.grid(False, axis="y")
    ax.tick_params(length=0)
    for yi, v in zip(y, df["pct_of_revenue"]):
        ax.text(float(v) + 1.2, yi, f"{v}%", va="center", fontsize=9, color=INK_2)
    return _fig_to_png_bytes(fig)
