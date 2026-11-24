"""Charts for the Time Trends report (Proposal 1).

Every chart is a function of the panel from lib.trends.panel() and a geography
("Maine" or a county name), so the county versions and any data refresh are
re-runs. Static PNGs for the report, light surface.

Styling follows the final report's charts: white background, centred plain
title, "Year" / units axis labels, dotted horizontal grid, left and bottom spines
only, frameless legend, brick / olive / ochre series colours.

Design rules:
  * one y-axis per plot - the report's two dual-axis charts are redrawn on a
    common unit (tax rates as % of value) or a common index (2012 = 100);
  * series colours follow the measure, fixed slot order, max three per plot;
    the report's three hues are re-stepped in lightness so red and green stay
    distinct under red-green colour blindness;
  * small circles mark every annual data point; gaps in the data (ACS 2020)
    are left as gaps;
  * a legend for >= 2 series; end-of-line value labels off (END_LABELS) to
    match the report; value labels take their series' colour, in a darker
    shade where the line colour is too light to read as text.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from . import trends as T

CHART_DIR = T.TRENDS_OUT / "charts"

# ------------------------------------------------------------------ tokens
SURFACE = "#ffffff"
INK, INK2, MUTED = "#000000", "#333333", "#6f6e69"
GRID, AXIS = "#cfcfcf", "#000000"
AXIS_LW = 0.6          # thin black axis lines
S1, S2, S3, S4 = "#8a2f25", "#6b8a52", "#d6a052", "#2f5d8c"   # brick, olive, ochre, navy (CVD-checked all-pairs)
# text set in a series' colour uses a darker shade where the line colour is too light to read
# as small text on white (olive 3.9:1 -> 5.1:1, ochre 2.3:1 -> 4.7:1)
TEXT_SHADE = {S2: "#5a7745", S3: "#9c6a22"}
REF = "#8a8880"
REF_LIGHT = "#aaa8a0"     # background reference line beside olive (REF is too close to S2 under CVD)                                   # reference series (e.g. CPI); only ever beside S1
MARKER_SIZE, GRID_MARKER_SIZE = 3.5, 2.2          # data-point circles, single charts / county grids
END_LABELS = False                                # value labels at line ends

# measure -> colour, fixed across every chart
COLOR = {
    "zhvi": S1, "redfin_med_price": S2, "med_home_value": S3, "fhfa": S4,
    "commitment": S1, "commitment_real": S3, "cpi": S2, "bea_sl_deflator": S2,
    "mill_rate": S2, "etr": S1,
    "avg_bill": S1, "homestead_bill": S2,
    "tax_share_income": S3,
}

YEARS_MVR = (2012, T.LATEST_MVR_YEAR)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9.5,
    "axes.edgecolor": AXIS, "axes.linewidth": AXIS_LW, "axes.labelcolor": INK,
    "axes.labelsize": 9.5, "axes.titlecolor": INK,
    "xtick.color": AXIS, "ytick.color": AXIS, "xtick.labelcolor": INK, "ytick.labelcolor": INK,
    "xtick.direction": "out", "ytick.direction": "out",
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "legend.frameon": False, "legend.fontsize": 9, "legend.handlelength": 2.6,
    "legend.numpoints": 1,
})

ACS_NOTE = "ACS 1-year estimates: none published for 2020 (due to covid)."
ACS_COUNTY_NOTE = " County estimates exist only for counties of 65,000+."
NOTE_GAP_PT = 6          # space between the x-axis label and the source note


# ------------------------------------------------------------------ helpers
def _geo(p: pd.DataFrame, geo: str, years=YEARS_MVR) -> pd.DataFrame:
    d = p[p["County"] == geo].set_index("Year").sort_index()
    return d.loc[years[0]:years[1]]


def _style_ax(ax, labelsize=None):
    ax.grid(axis="y", color=GRID, linewidth=0.6, linestyle=":")
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    # thin straight black lines: no anti-aliasing, so they snap to whole pixels and stay
    # solid black instead of blending into grey
    for sp in ax.spines.values():
        sp.set_antialiased(False)
    ax.tick_params(length=3, width=AXIS_LW, pad=3, **({"labelsize": labelsize} if labelsize else {}))


def _fig(n=1, w=7.6, h=4.3, sharey=False):
    fig, axes = plt.subplots(1, n, figsize=(w, h), sharey=sharey, squeeze=False)
    for ax in axes[0]:
        _style_ax(ax)
    return fig, list(axes[0])


def _geo_name(geo):
    return "Maine" if geo == "Maine" else f"{geo} County"


REF_H = 4.3   # figure height (in) the header/margin fractions below are written for


def _from_top(fig, frac):
    """A top-anchored position written as a fraction of a REF_H-tall figure, kept at
    the same distance (in inches) from the top edge whatever the figure's height."""
    return 1 - (1 - frac) * REF_H / fig.get_figheight()


def _header(fig, title, subtitle=None, note=None):
    """Centred plain title (re-centred over the plot area by _layout), optional
    grey subtitle, and a small source note (placed under the x-axis label by _place_note)."""
    fig.text(0.5, _from_top(fig, 0.975), title, ha="center", va="top", fontsize=12, color=INK, gid="center")
    if subtitle:
        fig.text(0.5, _from_top(fig, 0.915), subtitle, ha="center", va="top", fontsize=9, color=MUTED,
                 gid="center")
    if note:
        _note(fig, note)


def _wrap_measured(fig, par, fontsize, max_in):
    """Greedy word wrap using the rendered width of the text, so lines run to max_in inches."""
    from matplotlib.font_manager import FontProperties
    r, fp = fig.canvas.get_renderer(), FontProperties(size=fontsize)
    width_in = lambda s: r.get_text_width_height_descent(s, fp, ismath=False)[0] / fig.dpi
    lines, cur = [], ""
    for w in par.split(" "):
        cand = f"{cur} {w}" if cur else w
        if cur and width_in(cand) > max_in:
            lines.append(cur); cur = w
        else:
            cur = cand
    return "\n".join(lines + [cur])


def _note(fig, note, fill=False):
    """Source note. fill=True wraps by measured width across ~96% of the figure (used by the
    county grids); otherwise a conservative characters-per-inch estimate."""
    import textwrap
    width = int(fig.get_figwidth() * 17)          # ~characters per line at 7.5pt, 200 dpi
    note = note.replace("$", r"\$")              # a pair of $ would otherwise be read as mathtext
    # a newline in a note starts a new line; each line is wrapped on its own
    if fill:
        text = "\n".join(_wrap_measured(fig, par, 7.5, fig.get_figwidth() * 0.96) for par in note.split("\n"))
    else:
        text = "\n".join(textwrap.fill(par, width, break_on_hyphens=False) for par in note.split("\n"))
    fig.text(0.012, 0.015, text, ha="left", va="top",
             fontsize=7.5, color=MUTED, gid="note")


def _place_note(fig):
    """Move the source note to just below the lowest axis text (tick labels and
    x-axis label); the tight crop in savefig then drops the unused space."""
    notes = [t for t in fig.texts if t.get_gid() == "note"]
    if not notes:
        return
    r = fig.canvas.get_renderer()
    inv = fig.transFigure.inverted()
    boxes = [inv.transform(ax.get_tightbbox(r)) for ax in fig.axes if ax.get_visible()]
    low = min(b[0][1] for b in boxes)
    left = min(b[0][0] for b in boxes)        # left edge of the y-axis label: note starts flush with it
    for t in notes:
        gap = getattr(fig, "_note_gap_pt", NOTE_GAP_PT)
        t.set_position((left, low - gap / 72 / fig.get_figheight()))


def _savefig(fig, path):
    _place_note(fig)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def _layout(fig, top=0.865, bottom=0.25, right=0.96, left=0.12, wspace=0.28):
    fig.subplots_adjust(top=_from_top(fig, top), bottom=bottom * REF_H / fig.get_figheight(),
                        right=right, left=left, wspace=wspace)
    for t in fig.texts:
        if t.get_gid() == "center":
            t.set_x((left + right) / 2)


def _axis_labels(ax, ylabel, xlabel="Year"):
    ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)


def _line(ax, s: pd.Series, key: str, label: str, dashed=False, markers=True, ls=None):
    s = s.astype(float)
    if s.notna().sum() == 0:      # e.g. ACS series in a county below 65,000: no line, no legend entry
        return
    ax.plot(s.index, s.values, color=COLOR.get(key, key), lw=2,
            ls=ls or ((0, (4, 2)) if dashed else "-"), label=label, zorder=3,
            marker="o" if markers else None, ms=MARKER_SIZE, mew=0)


def _end_labels(ax, items, fmt, pad=0.4):
    """items: list of (series, text_prefix). Label each line at its last value,
    nudging apart labels that would overlap. No-op unless END_LABELS."""
    if not END_LABELS:
        return
    pts = []
    for s, prefix in items:
        s = s.dropna()
        if len(s):
            pts.append([s.index[-1], s.iloc[-1], f"{prefix}{fmt(s.iloc[-1])}"])
    if not pts:
        return
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.065
    pts.sort(key=lambda t: t[1])
    ys = [p[1] for p in pts]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < gap:
            ys[i] = ys[i - 1] + gap
    for (x, y, txt), yy in zip(pts, ys):
        ax.annotate(txt, (x, y), xytext=(x + pad, yy), textcoords="data",
                    va="center", ha="left", fontsize=8.5, color=INK, annotation_clip=False)


def _xyears(ax, start, end, step=2):
    ax.set_xlim(start - 0.5, end + 0.5)
    ax.set_xticks(range(start, end + 1, step))


def _usd(x, _=None):
    return f"${x/1e9:.1f}B" if abs(x) >= 1e9 else f"${x:,.0f}"


def _usd_label(x):
    """End-of-line labels: one more digit than the axis for billions."""
    return f"${x/1e9:.2f}B" if abs(x) >= 1e9 else _usd(x)


def _pct(d=1):
    return lambda x, _=None: f"{x*100:.{d}f}%"


def _save(fig, name, geo):
    out = CHART_DIR / ("state" if geo == "Maine" else "county") 
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}__{geo.lower().replace(' ', '_')}.png"
    _savefig(fig, path)
    return path


# ------------------------------------------------------------------ charts
def property_values(p, geo="Maine"):
    """1. Residential property values in dollars: Zillow, Redfin, ACS."""
    d = _geo(p, geo, (2000, T.LATEST_MVR_YEAR))
    fig, (ax,) = _fig()
    _line(ax, d["zhvi"], "zhvi", "Zillow Home Value Index")
    _line(ax, d["redfin_med_price"], "redfin_med_price", "Redfin median sale price")
    _line(ax, d["med_home_value"], "med_home_value", "ACS median home value")
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_usd))
    ax.set_ylim(0, None)
    _xyears(ax, 2000, T.LATEST_MVR_YEAR, 5)
    _axis_labels(ax, "Value ($)")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.02), borderaxespad=0, alignment="right")
    _end_labels(ax, [(d["zhvi"], ""), (d["redfin_med_price"], ""), (d["med_home_value"], "")], _usd)
    _header(fig, f"{_geo_name(geo)} property values, 2000–{T.LATEST_MVR_YEAR}", None,
            "Sources: Zillow ZHVI (all homes, mid-tier); Redfin Data Center (all residential, NSA; from 2016); "
            "ACS 1-year B25077. " + ACS_NOTE + ("" if geo == "Maine" else ACS_COUNTY_NOTE))
    _layout(fig, top=0.91)
    return _save(fig, "01_property_values", geo)


def property_value_index(p, geo="Maine", base=T.REDFIN_START):
    """1b. Property value growth, indexed to base year: Zillow, Redfin, FHFA (repeat sales), ACS.
    Base year defaults to Redfin's first comparable year so all four series share it."""
    d = _geo(p, geo, (2000, T.LATEST_MVR_YEAR))
    idx = lambda s: 100 * s / s.get(base, np.nan)
    series = [("zhvi", "zhvi", "Zillow Home Value Index"),
              ("redfin_med_price", "redfin_med_price", "Redfin median sale price"),
              ("fhfa_hpi_2000", "fhfa", "FHFA House Price Index (repeat sales)"),
              ("med_home_value", "med_home_value", "ACS median home value")]
    fig, (ax,) = _fig()
    for col, key, lab in series:
        _line(ax, idx(d[col]), key, lab)
    ax.axhline(100, color=GRID, lw=0.8, zorder=1)
    _xyears(ax, 2000, T.LATEST_MVR_YEAR, 5)
    _axis_labels(ax, f"Index ({base} = 100)")
    ax.legend(loc="upper left")
    _end_labels(ax, [(idx(d[col]), "") for col, _, _ in series], lambda v: f"{v:.0f}")
    _header(fig, f"{_geo_name(geo)} growth in property values, 2000–{T.LATEST_MVR_YEAR}",
            f"Each series divided by its own {base} value",
            "Sources: Zillow ZHVI; Redfin Data Center (all residential, NSA; from 2016); "
            "FHFA annual all-transactions HPI (developmental county/state indexes); "
            "ACS 1-year B25077. " + ACS_NOTE + ("" if geo == "Maine" else ACS_COUNTY_NOTE))
    _layout(fig)
    return _save(fig, "01b_property_value_index", geo)


COMMITMENT_H = 5.7   # the commitment charts carry growth labels, so they get a third more height
CAGR_PERIODS = [(2012, T.LATEST_MVR_YEAR), (2012, 2021), (2021, T.LATEST_MVR_YEAR)]


def _cagr(s: pd.Series, a: int, b: int) -> float:
    return (s[b] / s[a]) ** (1 / (b - a)) - 1


def _yoy_labels(ax, plotted: pd.Series, level: pd.Series, above=True, color=INK2):
    """Annotate each point (after the first) with its change from the prior year.
    above: bool, or a boolean Series by year (e.g. above wherever this line is the higher one)."""
    g = level.pct_change()
    for y in plotted.index[1:]:
        if pd.notna(g.get(y)) and pd.notna(plotted[y]):
            up = above if isinstance(above, bool) else bool(above.get(y, True))
            # centred on the point; a white outline keeps it readable where a steep line passes
            ax.annotate(f"{g[y]:+.1%}", (y, plotted[y]), xytext=(0, 7) if up else (0, -7),
                        textcoords="offset points", ha="center", va="bottom" if up else "top",
                        fontsize=7, color=color, zorder=4,
                        path_effects=[pe.withStroke(linewidth=2.5, foreground=SURFACE)])


def _cagr_box(ax, rows, loc=(0.02, 0.97)):
    """rows: list of (series label or None, level series). One line per CAGR_PERIODS entry."""
    lines = ["Compound annual growth"]
    for lab, s in rows:
        if lab:
            lines.append(lab)
        lines += [f"  {a}–{b}: {_cagr(s, a, b):+.1%}" for a, b in CAGR_PERIODS]
    ax.text(*loc, "\n".join(lines), transform=ax.transAxes, ha="left", va="top",
            fontsize=8, color=INK2, linespacing=1.35)


def _cagr_table(ax, rows, periods, title="Compound annual growth", loc=(0.02, 0.97),
                label_w=118, col_w=50, row_h=12, fontsize=8):
    """A small table in the upper-left of the plot: one row per (label, level series[, colour]),
    one column per (start, end) period. Laid out in points so it keeps its shape at any size."""
    kw = dict(xy=loc, xycoords="axes fraction", textcoords="offset points", fontsize=fontsize, zorder=5)
    # the title sits in the label column of the header row, level with the period headings
    y = 0
    ax.annotate(title, xytext=(0, y), ha="left", va="top", color=INK2, **kw)
    for j, (a, b) in enumerate(periods):
        ax.annotate(f"{a}–{str(b)[2:]}", xytext=(label_w + (j + 1) * col_w, y), ha="right", va="top",
                    color=INK2, **kw)
    for lab, lvl, *col in rows:
        col = col[0] if col else INK2
        y -= row_h
        ax.annotate(lab, xytext=(0, y), ha="left", va="top", color=col, **kw)
        for j, (a, b) in enumerate(periods):
            ax.annotate(f"{_cagr(lvl, a, b):+.1%}", xytext=(label_w + (j + 1) * col_w, y),
                        ha="right", va="top", color=col, **kw)


def commitment(p, geo="Maine", h=COMMITMENT_H, name="02_commitment"):
    """2. Property tax commitment (nominal) with year-on-year changes and CAGRs.
    h / name: e.g. commitment(p, h=4.3, name="02_commitment_standard") for a copy at the
    standard chart size."""
    d = _geo(p, geo)
    fig, (ax,) = _fig(h=h)
    c = d["commitment"]
    _line(ax, c, "commitment", "Tax commitment")
    _yoy_labels(ax, c, c)
    ax.yaxis.set_major_locator(mtick.MaxNLocator(nbins=9, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_usd))
    ax.set_ylim(c.min() * 0.95, c.max() * 1.04)
    _xyears(ax, *YEARS_MVR)
    _axis_labels(ax, "Commitment ($ billions)" if c.max() >= 1e9 else "Commitment ($)")
    _cagr_box(ax, [(None, c)])
    _header(fig, f"{_geo_name(geo)} property tax commitment, 2012–{T.LATEST_MVR_YEAR}",
            "Net amount to be raised by property tax (MVR Line 13), organized municipalities",
            f"Source: Maine Revenue Services, Municipal Valuation Returns 2012–{T.LATEST_MVR_YEAR}, Line 13. "
            "Labels show the change from the prior year.")
    _layout(fig)
    return _save(fig, name, geo)


INFLATION_CAGR_PERIODS = [(2012, 2021), (2021, T.LATEST_MVR_YEAR), (2012, T.LATEST_MVR_YEAR)]


def commitment_vs_cpi(p, geo="Maine", base=2021, h=COMMITMENT_H, name="03_commitment_vs_cpi"):
    """3. Commitment vs two price measures - Northeast CPI-U (households) and the BEA price
    index for state & local government purchases (cost of government) - all indexed to the
    base year, with year-on-year changes and a table of CAGRs. h / name as for commitment()."""
    d = _geo(p, geo)
    fig, (ax,) = _fig(h=h)
    ix = lambda c: 100 * d[c] / d.loc[base, c]
    ci, pi, bi = ix("commitment"), ix("cpi"), ix("bea_sl_deflator")
    c_com, c_bea = COLOR["commitment"], TEXT_SHADE.get(COLOR["bea_sl_deflator"], COLOR["bea_sl_deflator"])
    _line(ax, ci, "commitment", "Tax commitment")
    _line(ax, bi, "bea_sl_deflator", "State & local government prices (BEA)")
    # CPI is shown for context (prices households pay), as a thin grey reference line
    ax.plot(pi.index, pi.values, color=REF_LIGHT, lw=1.5, marker="o", ms=MARKER_SIZE - 0.5, mew=0,
            label="Northeast CPI-U", zorder=2)
    # commitment and BEA cross, so each year the higher of the two is labelled above and the
    # lower below; labels take their line's colour
    _yoy_labels(ax, ci, d["commitment"], above=ci >= bi, color=c_com)
    _yoy_labels(ax, bi, d["bea_sl_deflator"], above=bi > ci, color=c_bea)
    ax.axhline(100, color=GRID, lw=0.8, zorder=1)
    lo = min(ci.min(), pi.min(), bi.min()); hi = max(ci.max(), pi.max(), bi.max())
    ax.set_ylim(lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.06)
    _xyears(ax, *YEARS_MVR)
    _axis_labels(ax, f"Index ({base} = 100)")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.02), borderaxespad=0, alignment="right")
    _cagr_table(ax, [("Tax commitment", d["commitment"], c_com),
                     ("BEA state & local prices", d["bea_sl_deflator"], c_bea),
                     ("Northeast CPI-U", d["cpi"], MUTED)], INFLATION_CAGR_PERIODS)
    _header(fig, f"{_geo_name(geo)} property tax commitment vs. inflation, 2012–{T.LATEST_MVR_YEAR}",
            f"All series indexed to {base} = 100; labels show the change from the prior year",
            "Sources: MRS Municipal Valuation Returns (Line 13); BLS Northeast CPI-U all items "
            "(CUUR0100SA0), annual average, 2025 averages 11 months (no October 2025 release); "
            "BEA implicit price deflator for state and local government consumption expenditures "
            "and gross investment (national; FRED A829RD3A086NBEA).")
    _layout(fig)
    return _save(fig, name, geo)


# TRCF budget components: (panel column, legend label, fill colour), stacked bottom-up
# colours follow the report's original version of this chart (Tableau 10)
TRCF_UP = [("trcf_tif", "TIF", "#59a14f"), ("trcf_county", "County", "#4e79a7"),
           ("trcf_education", "Education", "#e15759"), ("trcf_municipal", "Municipality", "#f28e2b")]
TRCF_DOWN = [("trcf_revshare", "State revenue sharing", "#76b7b2"),
             ("trcf_other_rev", "Other revenues", "#edc948")]
# year-on-year change labels beside the large segments, in a darker shade of the fill
# (each >= 4.6:1 on white; the fills themselves are too light for small text)
TRCF_YOY = {"trcf_municipal": "#b15e0b", "trcf_education": "#db3437", "trcf_other_rev": "#8e720e"}
# where in its segment each label sits (0 = bottom, 1 = top); municipal labels go high,
# clear of the net-to-be-raised line that crosses the middle of that segment
TRCF_LABEL_POS = {"trcf_municipal": 0.8}


def _usd_b(x, _=None):
    if x == 0:
        return "$0"
    if abs(x) < 1e9:                                  # small counties: label in millions
        return f"{'−' if x < 0 else ''}${abs(x) / 1e6:,.0f}M"
    return f"{'−' if x < 0 else ''}${abs(x) / 1e9:.1f}B"


def appropriations(p, geo="Maine"):
    """3b. TRCF budget build-up: appropriations stacked above zero, offsetting revenues
    below, and the net to be raised by property tax as a line. TRCF data start in 2022."""
    y0, y1 = T.TRCF_FIRST_YEAR, T.LATEST_MVR_YEAR
    d = _geo(p, geo, (y0, y1))
    yrs = d.index.to_numpy()
    fig, (ax,) = _fig(w=9.6, h=5.0)
    handles, mid = {}, {}
    width = 0.55
    for stack, sign in ((TRCF_UP, 1), (TRCF_DOWN, -1)):
        base = np.zeros(len(yrs))
        for col, lab, colr in stack:
            v = sign * d[col].to_numpy(dtype=float)
            handles[lab] = ax.bar(yrs, v, width, bottom=base, color=colr, edgecolor=SURFACE, linewidth=1, zorder=3)
            mid[col] = base + v * TRCF_LABEL_POS.get(col, 0.5)   # label height within the segment
            base += v
    # each change is centred in the gap between the two years it compares, halfway between their segments
    for col, tcol in TRCF_YOY.items():
        g = d[col].pct_change().to_numpy()
        ym = (mid[col][:-1] + mid[col][1:]) / 2
        for x, yv, gv in zip(yrs[:-1], ym, g[1:]):
            if np.isfinite(gv):
                ax.text(x + 0.5, yv, f"{gv:+.1%}", ha="center", va="center", fontsize=7.5, color=tcol, zorder=6)
    net = d["trcf_net"].to_numpy(dtype=float)
    (handles["Net to be raised"],) = ax.plot(yrs, net, color=INK, lw=2, marker="D", ms=6, zorder=5)
    # its year-on-year changes in black, in the same gaps, just below the line's midpoint
    for x, a, b in zip(yrs[:-1], net[:-1], net[1:]):
        ax.annotate(f"{b / a - 1:+.1%}", (x + 0.5, (a + b) / 2), xytext=(0, -7), textcoords="offset points",
                    ha="center", va="top", fontsize=7.5, color=INK, zorder=6,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground=SURFACE)])
    ax.axhline(0, color=AXIS, lw=AXIS_LW, zorder=4, antialiased=False)
    ax.yaxis.set_major_locator(mtick.MaxNLocator(nbins=7, steps=[1, 2, 5, 10]))   # adapts to county scale
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_usd_b))
    ax.set_xticks(yrs)
    ax.set_xlim(yrs[0] - 0.6, yrs[-1] + 0.6)
    _axis_labels(ax, "$ billions")
    # legend in stack order (top to bottom)
    order = ["Net to be raised"] + [lab for _, lab, _ in TRCF_UP[::-1]] + [lab for _, lab, _ in TRCF_DOWN]
    ax.legend([handles[k] for k in order], order,
              loc="center left", bbox_to_anchor=(1.02, 0.5), borderaxespad=0, labelspacing=1.2)
    _header(fig, f"{_geo_name(geo)} appropriations, revenues, and net to be raised, {y0}–{y1}",
            "Appropriations above zero, offsetting revenues below; the line is the net to be raised",
            "Source: MRS Municipal Valuation Returns, Tax Rate Calculation Form (TRCF) Lines 7–15, organized "
            "municipalities; reported from 2022 only. Labels show the change from the prior year. Net to be raised (TRCF Line 15) = appropriations − revenue "
            "sharing − other revenues; it is met by the property tax commitment plus state homestead and BETE "
            "reimbursements, less overlay.")
    _layout(fig, right=0.78, left=0.09)   # plot runs wide; legend sits in the right margin
    return _save(fig, "03b_appropriations", geo)


RATE_LABEL_YEARS = (2012, 2020, T.LATEST_MVR_YEAR)


def tax_rates(p, geo="Maine"):
    """4. Nominal (mill) rate and effective tax rate on one axis, both as % of value."""
    d = _geo(p, geo)
    fig, (ax,) = _fig()
    _line(ax, d["mill_rate"], "mill_rate", "Nominal rate (mill rate, on assessed value)")
    _line(ax, d["etr"], "etr", "Effective tax rate (on market value)")
    # 1dp axis: tick steps of 0.1/0.2/0.5 points so every tick label is exact at one decimal
    ax.yaxis.set_major_locator(mtick.MaxNLocator(nbins=10, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_pct(1)))
    # values for the start, the pre-pandemic peak and the latest year, in each line's colour
    # (2dp: the two rates differ by less than 0.1 point in some years); higher line labelled above
    for col in ("mill_rate", "etr"):
        other = "etr" if col == "mill_rate" else "mill_rate"
        tcol = TEXT_SHADE.get(COLOR[col], COLOR[col])
        for y in RATE_LABEL_YEARS:
            if y in d.index and pd.notna(d.loc[y, col]):
                v = d.loc[y, col]
                up = v >= d.loc[y, other]
                # if the line leaves this point heading towards the label's side, shift the label left
                nxt = d[col].get(y + 1)
                into = (y != d.index[0] and pd.notna(nxt)          # (never at the first year: axis is there)
                        and ((nxt > v) if up else (nxt < v)))
                ax.annotate(f"{v:.2%}", (y, v), xytext=(-3 if into else 0, 7 if up else -7),
                            textcoords="offset points", ha="right" if into else "center",
                            va="bottom" if up else "top",
                            fontsize=8, color=tcol, zorder=6,
                            path_effects=[pe.withStroke(linewidth=2.5, foreground=SURFACE)])
    lo, hi = min(d.etr.min(), d.mill_rate.min()), max(d.etr.max(), d.mill_rate.max())
    ax.set_ylim(lo - (hi - lo) * 0.35, hi + (hi - lo) * 0.35)
    _xyears(ax, *YEARS_MVR)
    _axis_labels(ax, "Tax as % of value")
    ax.legend(loc="lower left")
    _end_labels(ax, [(d["mill_rate"], ""), (d["etr"], "")], _pct(2))
    _header(fig, f"{_geo_name(geo)} property tax rates, 2012–{T.LATEST_MVR_YEAR}",
            "Tax as a percent of property value. A mill rate of 13.5 = 1.35% of assessed value.",
            "Nominal rate = commitment ÷ taxable (assessed) value. Effective rate = commitment ÷ market value, "
            "where market value = taxable value ÷ certified ratio, by municipality. Source: MRS Municipal Valuation Returns.")
    _layout(fig)
    return _save(fig, "04_tax_rates", geo)


def tax_bills(p, geo="Maine"):
    """5. Average bill per parcel and the median homeowner's bill, nominal dollars.
    Median homeowner bill = (ACS 1-year median value - that year's statutory homestead
    exemption) x effective tax rate; see lib.trends.HOMESTEAD_EXEMPTION."""
    d = _geo(p, geo)
    fig, (ax,) = _fig(h=5.4)          # ~25% taller than the standard chart
    _line(ax, d["avg_bill"], "avg_bill", "Average bill per parcel")
    _line(ax, d["homestead_bill"], "homestead_bill", "Median homeowner with homestead exemption")
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_usd))
    ax.set_ylim(0, None)
    _xyears(ax, *YEARS_MVR)
    _axis_labels(ax, "Tax bill ($)")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.02), borderaxespad=0, alignment="right")
    _end_labels(ax, [(d["avg_bill"], ""), (d["homestead_bill"], "")], _usd)
    _header(fig, f"{_geo_name(geo)} property tax bills, 2012–{T.LATEST_MVR_YEAR}", None,
            "Average bill = commitment ÷ land parcels (MVR Line 42; towns not reporting parcels excluded; "
            "keying errors repaired).\n"
            "Median homeowner bill = (ACS 1-year median owner-occupied value − homestead exemption in force "
            "that year) × effective tax rate.\n" + ACS_NOTE)
    _layout(fig, top=0.91)
    return _save(fig, "05_tax_bills", geo)


def share_of_income(p, geo="Maine"):
    """6. Median homeowner's property tax as a share of owner-occupied median income,
    with every year's value labelled."""
    d = _geo(p, geo)
    fig, (ax,) = _fig()
    s = d["tax_share_income"]
    _line(ax, s, "tax_share_income", "Property tax ÷ household income")
    tcol = TEXT_SHADE.get(COLOR["tax_share_income"], COLOR["tax_share_income"])
    for y, v in s.dropna().items():
        ax.annotate(f"{v:.1%}", (y, v), xytext=(0, 6), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.5, color=tcol, zorder=6)
    ax.yaxis.set_major_locator(mtick.MultipleLocator(0.01))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_pct(1)))
    ax.set_ylim(0, max(0.06, np.nanmax(s.values) * 1.25))
    _xyears(ax, *YEARS_MVR)
    _axis_labels(ax, "Property tax as % of income")
    _header(fig, f"{_geo_name(geo)} property tax as a share of income, 2012–{T.LATEST_MVR_YEAR}",
            "Median homeowner with a homestead exemption",
            "Tax = (ACS 1-year median owner-occupied value − homestead exemption in force that year) × "
            "effective tax rate.\n"
            "Income = ACS 1-year median household income of owner-occupied households (B25119).\n" + ACS_NOTE)
    _layout(fig)
    return _save(fig, "06_share_of_income", geo)


ALL_CHARTS = [property_values, property_value_index, commitment, commitment_vs_cpi, appropriations,
              tax_rates, tax_bills, share_of_income]


def state_charts(p) -> list[Path]:
    return [f(p, "Maine") for f in ALL_CHARTS]


# ------------------------------------------------------------------ county small multiples
ACS1_COUNTIES = ["Androscoggin", "Aroostook", "Cumberland", "Kennebec", "Penobscot", "York"]


GRID_LW = 1.8          # line width in the small multiples


def _grid_frame(n, ncols, panel_h=1.95, sharey=True):
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(2.35 * ncols + 0.6, panel_h * nrows + 1.6),
                             sharex=True, sharey=sharey, squeeze=False)
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    return fig, axes, nrows


def _grid_finish(fig, nrows, handles, title, subtitle, note, name, tag="by_county", wspace=0.14):
    """Header, a single legend under it, source note, layout and save - shared by all grids.
    Positions are in inches from the top so every grid's header matches whatever its height."""
    h = fig.get_figheight()
    y_in = lambda inches: 1 - inches / h
    fig.text(0.525, y_in(0.12), title, ha="center", va="top", fontsize=12, color=INK)
    fig.text(0.525, y_in(0.42), subtitle, ha="center", va="top", fontsize=9, color=MUTED)
    labels = list(handles)
    fig.legend([handles[k] for k in labels], labels, loc="upper center", bbox_to_anchor=(0.525, y_in(0.68)),
               ncol=min(len(labels), 4), fontsize=9, handlelength=2.2, columnspacing=1.6)
    legend_rows = int(np.ceil(len(labels) / 4))
    _note(fig, note, fill=True)
    fig._note_gap_pt = 12                       # grids: caption sits a little further below the x-axis
    fig.subplots_adjust(top=y_in(1.05 + 0.22 * legend_rows), bottom=0.35 / h, left=0.07, right=0.98,
                        hspace=0.45, wspace=wspace)
    out = CHART_DIR / "county"; out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}__{tag}.png"
    _savefig(fig, path)
    return path


def _grid(p, counties, series, title, subtitle, note, yfmt, name, base=None,
          ylim=None, ncols=4, years=YEARS_MVR, xstep=4, tag="by_county", label_last=None, label_ends=None, label_gap=5,
          label_last_ha="right"):
    """Small multiples, one panel per county, shared y-axis, in the statewide charts' style.
    series: list of (column, colour key or hex, legend label[, style dict]) - style overrides
    lw / zorder / markers, e.g. a thinner grey reference line. base: index each series to that year = 100.
    label_last: (column, formatter) - print that series' final value in small text, in its colour, under its last point.
    label_ends: (column, formatter[, other column]) - print that series' first and last values below those points, in its colour;
    with another column, the label goes above the point wherever that line runs beneath it.
    label_gap: points between an end label and its data point."""
    fig, axes, nrows = _grid_frame(len(counties), ncols)
    handles = {}
    for ax, cty in zip(axes.flat, counties):
        d = _geo(p, cty, years)
        _style_ax(ax, labelsize=8)
        for col, key, lab, *style in series:
            st = {"lw": GRID_LW, "zorder": 3, **(style[0] if style else {})}
            s = d[col].astype(float)
            if base:
                s = 100 * s / s.get(base, np.nan)
            if s.notna().sum() == 0:
                continue
            (handles[lab],) = ax.plot(s.index, s.values, color=COLOR.get(key, key), label=lab,
                                      marker="o", ms=GRID_MARKER_SIZE, mew=0, **st)
            if label_last and col == label_last[0]:
                last = s.dropna()
                ax.annotate(label_last[1](last.iloc[-1]), (last.index[-1], last.iloc[-1]),
                            xytext=(0, -5), textcoords="offset points", ha="center", va="top",
                            fontsize=7, color=COLOR.get(key, key), zorder=6, annotation_clip=False)
            if label_ends and col == label_ends[0]:
                ends = s.dropna()
                other = d[label_ends[2]].astype(float) if len(label_ends) > 2 else None
                for i, ha in ((0, "left"), (-1, label_last_ha)):
                    x, yv = ends.index[i], ends.iloc[i]
                    # below the point, unless a second line (label_ends[2]) runs just beneath it
                    up = other is not None and np.isfinite(other.get(x, np.nan)) and other[x] <= yv
                    ax.annotate(label_ends[1](yv), (x, yv), xytext=(0, label_gap if up else -label_gap),
                                textcoords="offset points", ha=ha, va="bottom" if up else "top",
                                fontsize=7, color=COLOR.get(key, key), zorder=6, annotation_clip=False,
                                path_effects=[pe.withStroke(linewidth=2, foreground=SURFACE)])
        if base:
            ax.axhline(100, color=GRID, lw=0.6, zorder=1)
        ax.set_title(cty, fontsize=9.5, color=INK, pad=3)
        ax.yaxis.set_major_locator(mtick.MaxNLocator(nbins=5, steps=[1, 2, 5, 10]))
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(yfmt))
        ax.set_xticks(range(years[0], years[1] + 1, xstep))
    if ylim:
        axes[0, 0].set_ylim(*ylim)
    order = [lab for _, _, lab, *_ in series if lab in handles]
    return _grid_finish(fig, nrows, {k: handles[k] for k in order}, title, subtitle, note, name, tag)


def _approp_grid(p, counties, ncols=4, tag="by_county"):
    """TRCF budget build-up by county: the statewide appropriations chart as small multiples.
    Counties differ ~20-fold in size, so each panel has its own y-scale."""
    y0, y1 = T.TRCF_FIRST_YEAR, T.LATEST_MVR_YEAR
    fig, axes, nrows = _grid_frame(len(counties), ncols, panel_h=2.3, sharey=False)
    fig.set_figwidth(fig.get_figwidth() + 0.3)     # room for each panel's own y-axis labels
    handles, width = {}, 0.55
    for ax, cty in zip(axes.flat, counties):
        d = _geo(p, cty, (y0, y1))
        yrs = d.index.to_numpy()
        _style_ax(ax, labelsize=7.5)
        mid = {}
        for stack, sign in ((TRCF_UP, 1), (TRCF_DOWN, -1)):
            base = np.zeros(len(yrs))
            for col, lab, colr in stack:
                v = sign * d[col].to_numpy(dtype=float)
                handles[lab] = ax.bar(yrs, v, width, bottom=base, color=colr, edgecolor=SURFACE,
                                      linewidth=0.6, zorder=3)
                mid[col] = base + v * TRCF_LABEL_POS.get(col, 0.5)
                base += v
        # year-on-year change in municipal and education appropriations, in the gaps between bars,
        # as on the statewide chart
        for col in ("trcf_municipal", "trcf_education"):
            g = d[col].pct_change().to_numpy()
            ym = (mid[col][:-1] + mid[col][1:]) / 2
            for x, yv, gv in zip(yrs[:-1], ym, g[1:]):
                if np.isfinite(gv):
                    ax.text(x + 0.5, yv, f"{gv:+.0%}", ha="center", va="center", fontsize=6,
                            color=TRCF_YOY[col], zorder=6,
                            path_effects=[pe.withStroke(linewidth=2, foreground=SURFACE)])
        (handles["Net to be raised"],) = ax.plot(yrs, d["trcf_net"], color=INK, lw=1.5, marker="D", ms=3.5,
                                                 zorder=5)
        ax.axhline(0, color=AXIS, lw=AXIS_LW, zorder=4, antialiased=False)
        ax.set_title(cty, fontsize=9.5, color=INK, pad=3)
        ax.yaxis.set_major_locator(mtick.MaxNLocator(nbins=4, steps=[1, 2, 5, 10]))
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(_usd_b))
        ax.set_xticks(yrs)
        ax.set_xticklabels([f"'{str(y)[2:]}" for y in yrs])
        ax.set_xlim(yrs[0] - 0.5, yrs[-1] + 0.5)
    order = ["Net to be raised"] + [lab for _, lab, _ in TRCF_UP[::-1]] + [lab for _, lab, _ in TRCF_DOWN]
    return _grid_finish(
        fig, nrows, {k: handles[k] for k in order},
        f"Appropriations, revenues, and net to be raised by county, {y0}–{y1}",
        "Appropriations above zero, offsetting revenues below; each county on its own scale",
        "Source: MRS Municipal Valuation Returns, Tax Rate Calculation Form (TRCF) Lines 7–15, organized "
        "municipalities; reported from 2022 only.\n"
        "Net to be raised (TRCF Line 15) = appropriations − revenue sharing − other revenues. "
        "Labels show the change in municipal and education appropriations from the prior year.",
        "03b_appropriations", tag, wspace=0.24)


def county_grids(p, counties=None) -> list[Path]:
    """All county small multiples. counties=None draws all 16 (4 across, files *__by_county.png);
    a list draws just those, 3 across, e.g. county_grids(p, ACS1_COUNTIES) for the six counties
    with ACS 1-year data, where every panel has every series (files *__acs6_counties.png)."""
    if counties is None:
        cs, ncols, tag = sorted(c for c in p["County"].unique() if c != "Maine"), 4, "by_county"
    else:
        cs, ncols = list(counties), 3
        tag = "acs6_counties" if sorted(cs) == sorted(ACS1_COUNTIES) else "selected_counties"
    kw = {"ncols": ncols, "tag": tag}
    acs_scope = "" if counties is not None else " (six counties of 65,000+ only)"
    y = T.LATEST_MVR_YEAR
    mvr_src = f"Source: MRS Municipal Valuation Returns 2012–{y}."
    idx = lambda v, _=None: f"{v:.0f}"
    cpi_style = {"lw": 1.2, "zorder": 2}            # CPI as a thin grey reference line, as in the statewide chart
    vbase, ibase = T.REDFIN_START, 2021
    usd_k = lambda v, _=None: "$0" if v == 0 else f"${v / 1e3:,.0f}k"
    return [
        _grid(p, cs, [("zhvi", "zhvi", "Zillow Home Value Index"),
                      ("redfin_med_price", "redfin_med_price", "Redfin median sale price"),
                      ("med_home_value", "med_home_value", "ACS median home value")],
              f"Property values by county, 2012–{y}",
              "Nominal dollars; shared scale",
              "Sources: Zillow ZHVI (all homes, mid-tier); Redfin Data Center (all residential, NSA; from 2016); "
              f"ACS 1-year B25077{acs_scope}. " + ACS_NOTE,
              usd_k, "01_property_values", ylim=(0, None), **kw),
        _grid(p, cs, [("zhvi", "zhvi", "Zillow Home Value Index"),
                      ("redfin_med_price", "redfin_med_price", "Redfin median sale price"),
                      ("fhfa_hpi_2000", "fhfa", "FHFA House Price Index"),
                      ("med_home_value", "med_home_value", "ACS median home value")],
              f"Growth in property values by county, 2012–{y}",
              f"Each series divided by its own {vbase} value; shared scale",
              "Sources: Zillow ZHVI; Redfin Data Center (all residential, NSA; from 2016); FHFA annual "
              f"all-transactions HPI (developmental); ACS 1-year B25077{acs_scope}. " + ACS_NOTE,
              idx, "01b_property_value_index", base=vbase, **kw),
        _grid(p, cs, [("commitment", "commitment", "Tax commitment"),
                      ("bea_sl_deflator", "bea_sl_deflator", "State & local government prices (BEA)"),
                      ("cpi", REF_LIGHT, "Northeast CPI-U", cpi_style)],
              f"Property tax commitment vs. inflation by county, 2012–{y}",
              f"All series indexed to {ibase} = 100; shared scale",
              mvr_src + " BLS Northeast CPI-U all items (CUUR0100SA0), 2025 averages 11 months.\n"
              "BEA implicit price deflator for state and local government (national; FRED A829RD3A086NBEA).",
              idx, "03_commitment_vs_cpi", base=ibase, **kw),
        _approp_grid(p, cs, **kw),
        _grid(p, cs, [("mill_rate", "mill_rate", "Nominal rate (on assessed value)"),
                      ("etr", "etr", "Effective tax rate (on market value)")],
              f"Property tax rates by county, 2012–{y}",
              "Tax as a percent of property value; shared scale",
              mvr_src + "\nEffective rate = commitment ÷ market value (taxable value ÷ certified ratio, by municipality).",
              _pct(1), "04_tax_rates", ylim=(0.0078, None), label_last=("etr", lambda v: f"{v * 100:.2f}%"), **kw),
        _grid(p, cs, [("avg_bill", "avg_bill", "Average bill per parcel"),
                      ("homestead_bill", "homestead_bill", "Median homeowner with homestead exemption")],
              f"Property tax bills by county, 2012–{y}",
              "Shared scale",
              "Average bill = commitment ÷ land parcels (MVR Line 42; towns not reporting parcels excluded; "
              "keying errors repaired).\n"
              "Median homeowner bill = (ACS 1-year median owner-occupied value − homestead exemption in force "
              f"that year) × effective tax rate{';' + acs_scope if acs_scope else ''}.\n" + ACS_NOTE,
              _usd, "05_tax_bills", **kw,
              ylim=(500, None), label_ends=("homestead_bill", lambda v: f"${round(v / 50) * 50:,.0f}", "avg_bill"), label_gap=6,
              label_last_ha="center"),
        _grid(p, ACS1_COUNTIES, [("tax_share_income", "tax_share_income", "Property tax ÷ household income")],
              f"Property tax as a share of income by county, 2012–{y}",
              "Median homeowner with a homestead exemption; the six counties with ACS 1-year estimates",
              "Tax = (ACS 1-year median owner-occupied value − homestead exemption in force that year) × "
              "effective tax rate.\n"
              "Income = ACS 1-year median household income of owner-occupied households (B25119).\n" + ACS_NOTE,
              _pct(1), "06_share_of_income", ncols=3, ylim=(0, 0.07), tag=tag,
              label_ends=("tax_share_income", lambda v: f"{v * 100:.1f}%")),
    ]


def county_singles(p) -> list[Path]:
    cs = sorted(c for c in p["County"].unique() if c != "Maine")
    return [f(p, c) for c in cs for f in ALL_CHARTS]


# ------------------------------------------------------------------ growth by type of municipality
TYPE_LABELS = {
    "SC-adjacent": "Next to a service center", "Non-SC": "Not a service center",
    "Primary": "Primary service center", "Secondary": "Secondary service center",
    "Specialized": "Specialized service center", "Small": "Small service center",
    "bedroom": "Bedroom", "unclassified": "Unclassified (tiny towns)", "institutional": "Institutional",
    "farm_forest": "Farm & forest", "fishing": "Fishing", "diversified": "Diversified",
    "manufacturing": "Manufacturing", "tourism": "Tourism", "professional_services": "Professional services",
}
TYPE_TITLES = {"size": "by size of municipality", "service": "by service-center status",
               "economy": "by economic type"}


def commitment_growth_by_type(summary: pd.DataFrame, dim: str,
                              periods=((2012, 2019), (2019, 2025))) -> Path:
    """Annual growth in the summed property tax commitment for each category of one
    dimension of the Phase 2 typology, over two periods, against all municipalities."""
    d = summary[summary["dimension"] == dim].iloc[::-1]
    allrow = summary[summary["dimension"] == "all"].iloc[0]
    labels = [f"{TYPE_LABELS.get(c, c)} ({n})" for c, n in zip(d["category"], d["towns"])]
    fig, (ax,) = _fig(h=max(3.2, 0.42 * len(d) + 1.9))
    y, bh = np.arange(len(d)), 0.38
    for i, ((a, b), col) in enumerate(zip(periods, (S4, S1))):
        vals = d[f"cagr_{a}_{b}"].to_numpy()
        off = (0.5 - i) * bh
        ax.barh(y + off, vals, height=bh, color=col, label=f"{a}–{b}")
        for yy, v in zip(y + off, vals):
            ax.text(v + 0.0006, yy, f"{v*100:.1f}%", va="center", fontsize=7.5, color=INK2)
        ax.axvline(allrow[f"cagr_{a}_{b}"], color=col, lw=0.9, ls=(0, (3, 2)), alpha=0.8)
    ax.set_yticks(y, labels)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(_pct(0)))
    ax.set_xlim(0, max(0.08, d[[f"cagr_{a}_{b}" for a, b in periods]].max().max() + 0.012))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8.5, handlelength=1.2)
    _axis_labels(ax, None, "Compound annual growth in property tax commitment")
    _header(fig, f"Growth in property tax commitment {TYPE_TITLES[dim]}",
            "Annual growth rate, summed over the municipalities in each group (number in brackets)",
            note=("Dashed lines: all municipalities. A fixed set of 480 municipalities with a commitment "
                  "in every year 2012–2025; unorganized territories excluded. Nominal dollars. "
                  "Typology from the Phase 2 report. Source: Maine Revenue Services, Municipal Valuation Return."))
    _layout(fig, left=0.33, bottom=0.22)
    out = CHART_DIR / "types"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"07_commitment_growth__{dim}.png"
    _savefig(fig, path)
    return path


def municipal_appropriation_growth_by_type(summary: pd.DataFrame, dim: str, value: str = "trcf_municipal") -> Path:
    """2022-2025 annual growth in the municipal appropriation (TRCF Line 8) for each category,
    beside growth in the property tax commitment for the same towns and years."""
    d = summary[summary["dimension"] == dim].iloc[::-1]
    allrow = summary[summary["dimension"] == "all"].iloc[0]
    labels = [f"{TYPE_LABELS.get(c, c)} ({n})" for c, n in zip(d["category"], d["towns"])]
    fig, (ax,) = _fig(h=max(3.2, 0.42 * len(d) + 1.9))
    y, bh = np.arange(len(d)), 0.38
    series = [(f"cagr_{value}", S1, "Municipal appropriation"), ("cagr_commitment", REF_LIGHT, "Property tax commitment")]
    for i, (col, color, lab) in enumerate(series):
        vals = d[col].to_numpy()
        off = (0.5 - i) * bh
        ax.barh(y + off, vals, height=bh, color=color, label=lab)
        for yy, v in zip(y + off, vals):
            ax.text(v + 0.0008, yy, f"{v*100:.1f}%", va="center", fontsize=7.5, color=INK2)
        ax.axvline(allrow[col], color=color if color != REF_LIGHT else MUTED, lw=0.9, ls=(0, (3, 2)), alpha=0.8)
    ax.set_yticks(y, labels)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(_pct(0)))
    ax.set_xlim(0, max(0.14, d[[c for c, _, _ in series]].max().max() + 0.03))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8.5, handlelength=1.2)
    _axis_labels(ax, None, "Compound annual growth, 2022–2025")
    n = int(allrow["towns"])
    _header(fig, f"Growth in municipal appropriations {TYPE_TITLES[dim]}, 2022–2025",
            "Annual growth rate, summed over the municipalities in each group (number in brackets)",
            note=(f"Municipal appropriation = Tax Rate Calculation Form Line 8, before offsetting revenues; excludes "
                  f"education, county tax and TIF. Dashed lines: all municipalities. A fixed set of {n} municipalities "
                  "reporting Line 8 in every year 2022–2025; unorganized territories excluded. Nominal dollars. "
                  "Typology from the Phase 2 report. Source: Maine Revenue Services, Municipal Valuation Return."))
    _layout(fig, left=0.33, bottom=0.22)
    out = CHART_DIR / "types"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"08_municipal_appropriation_growth__{dim}.png"
    _savefig(fig, path)
    return path


def _town_cagr(m: pd.DataFrame, value: str, first: int, last: int) -> pd.Series:
    w = m.pivot_table(index="muni_id", columns="Year", values=value, aggfunc="sum")
    return (w[last] / w[first]) ** (1 / (last - first)) - 1


def municipal_appropriation_change_distribution(m: pd.DataFrame, value: str = "trcf_municipal",
                                                first: int = 2022, last: int = 2025) -> Path:
    """Histogram of each town's compound annual growth in the municipal appropriation
    (TRCF Line 8), first->last, with the median town and Northeast CPI marked."""
    cagr = _town_cagr(m, value, first, last)
    w = m.pivot_table(index="muni_id", columns="Year", values=value, aggfunc="sum")
    tot = (w[last].sum() / w[first].sum()) ** (1 / (last - first)) - 1
    cpi = T.load_cpi().set_index("Year")["cpi"]
    infl = (cpi[last] / cpi[first]) ** (1 / (last - first)) - 1
    lo, hi, step = -0.10, 0.30, 0.01
    bins = np.arange(lo - step, hi + 2 * step, step)
    fig, (ax,) = _fig(h=4.6)
    ax.hist(cagr.clip(lo - step / 2, hi + step / 2), bins=bins, color=S4, edgecolor=SURFACE, linewidth=0.6)
    ymax = ax.get_ylim()[1] * 1.18
    ax.set_ylim(0, ymax)
    for x, lab, col, ha, dx in ((infl, f"Inflation {infl*100:.1f}%", MUTED, "right", -0.003),
                                (cagr.median(), f"Median town {cagr.median()*100:.1f}%", S1, "left", 0.003)):
        ax.axvline(x, color=col, lw=1.4, ls=(0, (4, 2)))
        ax.text(x + dx, ymax * 0.97, lab, ha=ha, va="top", fontsize=8, color=TEXT_SHADE.get(col, col))
    ax.set_xlim(lo - 1.5 * step, hi + 1.5 * step)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x*100:.0f}%"))
    n_lo, n_hi = int((cagr < lo).sum()), int((cagr > hi).sum())
    ax.grid(axis="x", visible=False)
    _axis_labels(ax, "Number of municipalities", f"Compound annual growth in municipal appropriation, {first}–{last}")
    q1, q3 = cagr.quantile([0.25, 0.75])
    above = int((cagr > infl).sum())
    _header(fig, f"How fast each municipality's budget grew, {first}–{last}",
            f"{len(cagr)} municipalities: median {cagr.median()*100:.1f}% a year, half between {q1*100:.1f}% and "
            f"{q3*100:.1f}%; {above} grew faster than inflation",
            note=(f"Municipal appropriation = Tax Rate Calculation Form Line 8, before offsetting revenues; excludes "
                  f"education, county tax and TIF. All towns combined: {tot*100:.1f}% a year. Bars are 1-point bands; "
                  f"the end bars include {n_lo} towns below {lo*100:.0f}% and {n_hi} above {hi*100:.0f}%. Inflation = "
                  "Northeast CPI-U. Unorganized territories excluded. Source: Maine Revenue Services, Municipal "
                  "Valuation Return."))
    _layout(fig, left=0.11, bottom=0.2)
    out = CHART_DIR / "types"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "09_municipal_appropriation_cagr_distribution.png"
    _savefig(fig, path)
    return path


# Three-panel town-type format of the interim report (maine-rfp 09-report-charttemplates.ipynb,
# chart_by_munitype): simple average across towns with standard-error bars, one panel each for
# size, service-center designation and economy, a dotted all-municipalities reference line.
REPORT_PANEL_COLORS = ["#A63228", "#D4874E", "#5C7A45"]      # crimson, amber, spruce
REPORT_PANELS = [
    ("MuniType_Size", "Town/City Size",
     ["Tiny Town", "Small Town", "Medium Town", "Large Town", "Small City", "City"], {}),
    ("MuniType_Service", "Service Center Designation",
     ["Non-SC", "SC-adjacent", "Small", "Specialized", "Secondary", "Primary"], {}),
    ("MuniType_Economy", "Economy",
     ["farm_forest", "fishing", "manufacturing", "institutional", "tourism", "professional_services",
      "diversified", "bedroom"],
     {"farm_forest": "Farm/Forest", "fishing": "Fishing", "manufacturing": "Manufacturing",
      "institutional": "Institutional", "tourism": "Tourism", "professional_services": "Professional",
      "diversified": "Diversified", "bedroom": "Bedroom"}),
]


def _median_se(s: pd.Series, reps: int = 2000, seed: int = 0) -> float:
    """Bootstrap standard error of the median (fixed seed, so charts rebuild identically)."""
    v = s.dropna().to_numpy()
    rng = np.random.default_rng(seed)
    return float(np.median(rng.choice(v, size=(reps, len(v)), replace=True), axis=1).std(ddof=1))


def municipal_appropriation_cagr_by_munitype(m: pd.DataFrame, value: str = "trcf_municipal",
                                             first: int = 2022, last: int = 2025, stat: str = "mean",
                                             plot_scale: float = 1.0) -> Path:
    """Average (stat="mean", with standard-error bars) or median (stat="median") town CAGR in the
    municipal appropriation by size, service-center designation and economy, in the interim
    report's three-panel format. The median is not pulled up by the handful of small towns whose
    budgets grew very fast, so it is the better guide to the typical town.
    plot_scale shrinks the bars' height (e.g. 0.55 for a version ~30% shorter overall), saved as *_short.png."""
    import textwrap
    from matplotlib.transforms import blended_transform_factory
    d = m.drop_duplicates("muni_id").set_index("muni_id")
    d["_val"] = _town_cagr(m, value, first, last)
    ref = d["_val"].agg(stat)
    word = {"mean": "Average", "median": "Median"}[stat]
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 11.0 / 1.618 * (2 / 3) * plot_scale + 1.3), sharey=True,
                             gridspec_kw={"wspace": 0.06})
    for ax, (col, title, order, labels), color in zip(axes, REPORT_PANELS, REPORT_PANEL_COLORS):
        g = d.groupby(col)["_val"]
        means, sems, ns = g.agg(stat), (g.sem() if stat == "mean" else g.apply(_median_se)), g.size()
        cats = [c for c in order if c in means.index]
        x = np.arange(len(cats))
        ax.bar(x, means.reindex(cats), yerr=sems.reindex(cats), capsize=4,
               color=color, ecolor="#777777",
               edgecolor="white", linewidth=0.5, zorder=3)
        ax.axhline(ref, color="#888888", linestyle=":", linewidth=1.4, zorder=5)
        ax.set_xticks(x, [f"{labels.get(c, c)} ({ns[c]})" for c in cats], rotation=90, ha="center", va="top",
                      fontsize=11)
        ax.set_title(title, fontsize=11, pad=10)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", linestyle="--", linewidth=0.4, alpha=0.5, zorder=1)
        ax.grid(axis="x", visible=False)
        ax.set_axisbelow(True)
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v*100:.0f}%"))
    axes[0].set_ylabel(textwrap.fill(f"{word} annual growth in municipal appropriation, {first}–{last}", 42),
                       fontsize=10)
    fig.suptitle(f"Growth in municipal appropriations by type of municipality, {first}–{last}", fontsize=12,
                 y=0.985 + 0.32 / fig.get_figheight())          # a fixed 0.32in above the subtitle at any height
    fig.text(0.5, 0.985, f"{word} of each municipality's annual growth; dotted line = all {len(d)} municipalities "
             f"({ref*100:.1f}%)", ha="center", va="bottom", fontsize=9, color=MUTED)
    fig.tight_layout()
    bars = ("simple average of each municipality's compound annual growth" if stat == "mean"
            else "median of the municipalities' compound annual growth rates")
    note = (f"Bars: {bars} in the municipal appropriation "
                f"(Tax Rate Calculation Form Line 8, before offsetting revenues; excludes education, county tax and "
                f"TIF), with {'standard-error bars' if stat == 'mean' else 'bootstrapped standard errors of the median'}; "
                f"number of municipalities in brackets. The 85 tiny towns are absent "
                f"from the Economy panel (the economic typology does not classify them). Unorganized territories excluded. "
                f"Source: Maine Revenue Services, Municipal Valuation Return.")
    r = fig.canvas.get_renderer()
    span_in = (axes[-1].get_position().x1 - axes[0].get_tightbbox(r).transformed(fig.transFigure.inverted()).x0) \
        * fig.get_figwidth()
    fig.text(0.012, 0.015, _wrap_measured(fig, note, 7.5, span_in), ha="left", va="top",
             fontsize=7.5, color=MUTED, gid="note")
    out = CHART_DIR / "types"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"10{'' if stat == 'mean' else 'b'}_municipal_appropriation_cagr_by_munitype{'' if stat == 'mean' else '_median'}{'' if plot_scale == 1.0 else '_short'}.png"
    _savefig(fig, path)
    return path
