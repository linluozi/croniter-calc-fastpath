"""Generate the figures for the README from the recorded benchmark JSON.

All labels are English ASCII on purpose: the figures are served from GitHub and
CJK glyphs would render as boxes on machines without a CJK font.

Inputs : harness/results_ab.json, results_ba.json, results_aa.json
Outputs: docs/figures/*.png
"""

import json
import pathlib
import statistics

# The CI type-check job installs mypy but not matplotlib (the figures are a
# build artefact, regenerated on demand), so the whole import block is opaque
# to mypy rather than each module being annotated one by one.
import matplotlib  # type: ignore[import-not-found]
import matplotlib.ticker  # type: ignore[import-not-found]

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # type: ignore[import-not-found]
from matplotlib.lines import Line2D  # type: ignore[import-not-found]

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "docs" / "figures"

INK = "#2b2119"
PAPER = "#faf6f0"
AMBER = "#c8892b"
TERRACOTTA = "#b4552f"
OLIVE = "#6b6b3a"
MUTED = "#8a7a68"
GRID = "#e3d9c9"

# Order used in every figure, so the reader can move between them.
ORDER = [
    "minutely",
    "every5min",
    "hourly",
    "daily",
    "every3hours",
    "dom_step",
    "weekday",
    "nth_weekday",
    "nth_weekday_5",
    "lastday",
    "nearest_wd",
    "prev_minutely",
    "prev_sparse",
    "second_step",
]

LABEL = {
    "minutely": "* * * * *  (next)",
    "every5min": "*/5 * * * *",
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "every3hours": "0 */3 * * *",
    "dom_step": "0 0 */3 * *",
    "weekday": "0 0 * * sat",
    "nth_weekday": "0 0 * * 1#2",
    "nth_weekday_5": "0 0 * * 5#5",
    "lastday": "0 0 L * *",
    "nearest_wd": "0 0 15W * *",
    "prev_minutely": "* * * * *  (prev)",
    "prev_sparse": "0 0 * * sat,sun  (prev)",
    "second_step": "*/15 * * * * *  (seconds)",
}


def load(name):
    with open(HERE / name, encoding="utf-8") as fh:
        return json.load(fh)


def style():
    plt.rcParams.update(
        {
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def fig_speedup(ab, ba):
    """Per-workload speed-up, forward run as a bar, reverse run as a marker."""
    keys = ORDER
    fwd = [ab["workloads"][k]["ratio_median"] for k in keys]
    rev = [1.0 / ba["workloads"][k]["ratio_median"] for k in keys]

    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    y = range(len(keys))
    ax.barh(
        list(y),
        fwd,
        height=0.62,
        color=AMBER,
        edgecolor=INK,
        linewidth=0.6,
        label="forward run (upstream vs patched)",
        zorder=3,
    )
    ax.plot(
        rev,
        list(y),
        "D",
        color=TERRACOTTA,
        markersize=6.5,
        markeredgecolor=INK,
        markeredgewidth=0.7,
        label="reverse run (arms swapped)",
        zorder=4,
    )

    for i, (f, r) in enumerate(zip(fwd, rev)):
        ax.text(
            max(f, r) + 0.06,
            i,
            f"{f:.2f}x",
            va="center",
            ha="left",
            fontsize=9,
            color=INK,
            zorder=5,
        )

    ax.axvline(1.0, color=MUTED, linewidth=1.1, linestyle=(0, (3, 3)), zorder=2)
    ax.annotate(
        "no change",
        xy=(1.0, -0.75),
        xycoords=("data", "data"),
        ha="center",
        va="bottom",
        fontsize=8.5,
        color=MUTED,
        annotation_clip=False,
    )
    ax.set_yticks(list(y))
    ax.set_yticklabels([LABEL[k] for k in keys], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("speed-up (upstream time / patched time), median of 9 rounds")
    ax.set_xlim(0, max(max(fwd), max(rev)) * 1.22)
    ax.set_title("croniter get_next()/get_prev(): per-workload speed-up", pad=14)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.105), ncol=2, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0.012, 0.03, 1, 1))
    fig.savefig(OUT / "speedup.png", dpi=170)
    plt.close(fig)


def fig_noise(ab, aa):
    """Effect size against the A/A noise floor, same axis for both."""
    keys = ORDER
    rows = []
    for k in keys:
        eff = ab["workloads"][k]
        noise = aa["workloads"][k]
        n_ratios = [u / p for u, p in zip(noise["upstream_ms"], noise["patched_ms"])]
        e_ratios = [u / p for u, p in zip(eff["upstream_ms"], eff["patched_ms"])]
        rows.append(
            {
                "key": k,
                "eff_med": statistics.median(e_ratios),
                "eff_q1": statistics.quantiles(e_ratios, n=4)[0],
                "eff_q3": statistics.quantiles(e_ratios, n=4)[2],
                "eff_lo": min(e_ratios),
                "eff_hi": max(e_ratios),
                "n_med": statistics.median(n_ratios),
                "n_q1": statistics.quantiles(n_ratios, n=4)[0],
                "n_q3": statistics.quantiles(n_ratios, n=4)[2],
                "n_lo": min(n_ratios),
                "n_hi": max(n_ratios),
            }
        )

    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    for i, row in enumerate(rows):
        y = i
        # noise band first, so the effect bar sits on top
        ax.plot(
            [row["n_lo"], row["n_hi"]],
            [y - 0.17, y - 0.17],
            color=MUTED,
            linewidth=1.0,
            solid_capstyle="butt",
            zorder=3,
        )
        ax.plot(
            [row["n_q1"], row["n_q3"]],
            [y - 0.17, y - 0.17],
            color=MUTED,
            linewidth=7,
            solid_capstyle="butt",
            alpha=0.45,
            zorder=3,
        )
        ax.plot(
            row["n_med"],
            y - 0.17,
            "o",
            color=PAPER,
            markersize=5,
            markeredgecolor=MUTED,
            markeredgewidth=1.4,
            zorder=4,
        )

        ax.plot(
            [row["eff_lo"], row["eff_hi"]],
            [y + 0.17, y + 0.17],
            color=TERRACOTTA,
            linewidth=1.0,
            solid_capstyle="butt",
            zorder=3,
        )
        ax.plot(
            [row["eff_q1"], row["eff_q3"]],
            [y + 0.17, y + 0.17],
            color=TERRACOTTA,
            linewidth=7,
            solid_capstyle="butt",
            alpha=0.55,
            zorder=3,
        )
        ax.plot(
            row["eff_med"],
            y + 0.17,
            "o",
            color=PAPER,
            markersize=5,
            markeredgecolor=TERRACOTTA,
            markeredgewidth=1.4,
            zorder=4,
        )
        ax.text(
            row["eff_hi"] * 1.03,
            y + 0.17,
            f"{row['eff_med']:.2f}x",
            va="center",
            fontsize=8.5,
            color=INK,
            zorder=5,
        )

    ax.axvline(1.0, color=INK, linewidth=1.0, zorder=2)
    ax.set_xscale("log")
    ticks = [0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0]
    ax.xaxis.set_major_locator(matplotlib.ticker.FixedLocator(ticks))
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([LABEL[r["key"]] for r in rows], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("ratio of per-round times (log scale)")
    ax.set_title("Effect size versus measured noise floor", pad=14)

    handles = [
        Line2D(
            [0],
            [0],
            color=MUTED,
            linewidth=7,
            alpha=0.45,
            label="A/A noise floor (same file both arms), IQR",
        ),
        Line2D(
            [0], [0], color=TERRACOTTA, linewidth=7, alpha=0.55, label="measured speed-up, IQR"
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            color=PAPER,
            markeredgecolor=INK,
            markersize=5.5,
            label="median (thin line = full range)",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.11),
        ncol=1,
        frameon=False,
        fontsize=9,
    )
    fig.tight_layout(rect=(0.012, 0.02, 1, 1))
    fig.savefig(OUT / "noise-floor.png", dpi=170)
    plt.close(fig)


def fig_attribution():
    """Which of the two edits pays for which workload."""
    arms = {
        "weekday only": {
            "minutely": 1.013,
            "daily": 0.966,
            "weekday": 0.993,
            "nth_weekday": 1.541,
            "nth_weekday_5": 1.447,
            "lastday": 0.980,
            "nearest_wd": 1.002,
        },
        "timedelta only": {
            "minutely": 3.122,
            "daily": 2.590,
            "weekday": 2.457,
            "nth_weekday": 1.735,
            "nth_weekday_5": 1.744,
            "lastday": 2.497,
            "nearest_wd": 2.406,
        },
        "both (delivered)": {
            "minutely": 3.263,
            "daily": 2.535,
            "weekday": 2.523,
            "nth_weekday": 3.392,
            "nth_weekday_5": 3.724,
            "lastday": 2.472,
            "nearest_wd": 2.385,
        },
    }
    keys = [
        "minutely",
        "daily",
        "weekday",
        "nth_weekday",
        "nth_weekday_5",
        "lastday",
        "nearest_wd",
    ]
    short = {
        "minutely": "* * * * *",
        "daily": "0 0 * * *",
        "weekday": "0 0 * * sat",
        "nth_weekday": "0 0 * * 1#2",
        "nth_weekday_5": "0 0 * * 5#5",
        "lastday": "0 0 L * *",
        "nearest_wd": "0 0 15W * *",
    }
    colors = [OLIVE, AMBER, TERRACOTTA]
    width = 0.26

    fig, ax = plt.subplots(figsize=(9.4, 4.9))
    x = list(range(len(keys)))
    for j, (name, values) in enumerate(arms.items()):
        offsets = [i + (j - 1) * width for i in x]
        bars = ax.bar(
            offsets,
            [values[k] for k in keys],
            width=width,
            color=colors[j],
            edgecolor=INK,
            linewidth=0.6,
            label=name,
            zorder=3,
        )
        for bar, k in zip(bars, keys):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.04,
                f"{values[k]:.2f}",
                ha="center",
                va="bottom",
                fontsize=7.4,
                color=INK,
                zorder=4,
                rotation=90,
            )

    ax.axhline(1.0, color=MUTED, linewidth=1.1, linestyle=(0, (3, 3)), zorder=2)

    ax.set_xticks(x)
    ax.set_xticklabels([short[k] for k in keys], fontsize=9)
    ax.set_ylabel("speed-up vs pristine upstream")
    ax.set_ylim(0, 4.6)
    ax.set_title("Attribution: two single-change arms on top of upstream", pad=14)
    handles, labels = ax.get_legend_handles_labels()
    handles.insert(
        0,
        Line2D(
            [0], [0], color=MUTED, linewidth=1.1, linestyle=(0, (3, 3)), label="no change (1.00x)"
        ),
    )
    labels.insert(0, "no change (1.00x)")
    ax.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=4,
        frameon=False,
        fontsize=9,
    )
    fig.tight_layout(rect=(0.012, 0.02, 1, 1))
    fig.savefig(OUT / "attribution.png", dpi=170)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    style()
    ab, ba, aa = load("results_ab.json"), load("results_ba.json"), load("results_aa.json")
    fig_speedup(ab, ba)
    fig_noise(ab, aa)
    fig_attribution()
    for p in sorted(OUT.glob("*.png")):
        print(p.name, p.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
