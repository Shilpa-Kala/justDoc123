#!/usr/bin/env python3
"""
Business Presentation Generator
Reads a slides_plan.json and produces a polished .pptx file with:
  - Professional corporate themes
  - Auto-generated diagrams (flowcharts, timelines, pie/bar charts, comparisons)
  - Consistent typography, colors, and layout
  - Speaker notes on every content slide
"""

import json
import sys
import os
import re
import math
import io
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt
    import pptx.oxml.ns as nsmap
    from lxml import etree
except ImportError:
    print("Installing python-pptx...")
    os.system("pip install python-pptx -q")
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    import numpy as np
except ImportError:
    print("Installing matplotlib...")
    os.system("pip install matplotlib -q")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    import numpy as np

try:
    from PIL import Image
except ImportError:
    os.system("pip install Pillow -q")
    from PIL import Image


# ──────────────────────────────────────────────────────────────
# THEME DEFINITIONS
# ──────────────────────────────────────────────────────────────

THEMES = {
    "corporate": {
        "primary":     RGBColor(0x1A, 0x3A, 0x5C),   # Deep navy
        "secondary":   RGBColor(0x2E, 0x86, 0xC1),   # Bright blue
        "accent":      RGBColor(0xF3, 0x9C, 0x12),   # Gold
        "background":  RGBColor(0xF8, 0xF9, 0xFA),   # Off-white
        "surface":     RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark":   RGBColor(0x1A, 0x1A, 0x2E),
        "text_light":  RGBColor(0xFF, 0xFF, 0xFF),
        "mpl_palette": ["#1A3A5C", "#2E86C1", "#F39C12", "#27AE60", "#8E44AD", "#E74C3C"],
    },
    "technology": {
        "primary":     RGBColor(0x0D, 0x1B, 0x2A),
        "secondary":   RGBColor(0x00, 0xB4, 0xD8),
        "accent":      RGBColor(0x00, 0xF5, 0xD4),
        "background":  RGBColor(0xF0, 0xF4, 0xF8),
        "surface":     RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark":   RGBColor(0x0D, 0x1B, 0x2A),
        "text_light":  RGBColor(0xFF, 0xFF, 0xFF),
        "mpl_palette": ["#0D1B2A", "#00B4D8", "#00F5D4", "#90E0EF", "#48CAE4", "#0096C7"],
    },
    "healthcare": {
        "primary":     RGBColor(0x00, 0x60, 0x64),
        "secondary":   RGBColor(0x00, 0x97, 0x7D),
        "accent":      RGBColor(0xFF, 0xC4, 0x00),
        "background":  RGBColor(0xF1, 0xF8, 0xF6),
        "surface":     RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark":   RGBColor(0x1A, 0x2E, 0x2B),
        "text_light":  RGBColor(0xFF, 0xFF, 0xFF),
        "mpl_palette": ["#006064", "#00977D", "#FFC400", "#4CAF50", "#26A69A", "#80CBC4"],
    },
    "finance": {
        "primary":     RGBColor(0x1B, 0x26, 0x31),
        "secondary":   RGBColor(0xC9, 0xA0, 0x2F),
        "accent":      RGBColor(0x4A, 0x90, 0xD9),
        "background":  RGBColor(0xF5, 0xF5, 0xF0),
        "surface":     RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark":   RGBColor(0x1B, 0x26, 0x31),
        "text_light":  RGBColor(0xFF, 0xFF, 0xFF),
        "mpl_palette": ["#1B2631", "#C9A02F", "#4A90D9", "#7FB3D3", "#A9CCE3", "#D6EAF8"],
    },
    "general": {
        "primary":     RGBColor(0x34, 0x49, 0x5E),
        "secondary":   RGBColor(0x5D, 0xAD, 0xE8),
        "accent":      RGBColor(0xEB, 0x87, 0x4B),
        "background":  RGBColor(0xF7, 0xF9, 0xFC),
        "surface":     RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark":   RGBColor(0x2C, 0x3E, 0x50),
        "text_light":  RGBColor(0xFF, 0xFF, 0xFF),
        "mpl_palette": ["#34495E", "#5DADE8", "#EB874B", "#2ECC71", "#9B59B6", "#E74C3C"],
    },
}

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


# ──────────────────────────────────────────────────────────────
# HELPER: ADD SHAPES / TEXT
# ──────────────────────────────────────────────────────────────

def rgb_to_hex(rgb: RGBColor) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def add_rect(slide, x, y, w, h, fill_rgb, transparency=0):
    shape = slide.shapes.add_shape(1, x, y, w, h)  # MSO_SHAPE_TYPE.RECTANGLE
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_rgb
    shape.line.fill.background()
    if transparency:
        shape.fill.fore_color.theme_color = None
        # Set transparency via XML
        sp = shape._element
        solidFill = sp.find('.//' + nsmap.qn('a:solidFill'))
        if solidFill is not None:
            srgb = solidFill.find(nsmap.qn('a:srgbClr'))
            if srgb is None:
                srgb = solidFill.find(nsmap.qn('a:schemeClr'))
            if srgb is not None:
                alpha = etree.SubElement(srgb, nsmap.qn('a:alpha'))
                alpha.set('val', str(int((1 - transparency) * 100000)))
    return shape


def add_textbox(slide, text, x, y, w, h, font_size, bold=False, italic=False,
                color=None, align=PP_ALIGN.LEFT, wrap=True):
    txBox = slide.shapes.add_textbox(x, y, w, h)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color
    return txBox


def set_slide_background(slide, rgb: RGBColor):
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = rgb


# ──────────────────────────────────────────────────────────────
# DIAGRAM GENERATORS (matplotlib → PNG → embedded)
# ──────────────────────────────────────────────────────────────

def fig_to_stream(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


def make_flowchart(steps: list, palette: list, bg: str = "#FFFFFF") -> io.BytesIO:
    n = len(steps)
    fig, ax = plt.subplots(figsize=(10, max(4, n * 1.4)))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.axis("off")

    box_w, box_h = 5.0, 0.7
    gap = 0.45
    x0 = 2.5
    total_h = n * box_h + (n - 1) * gap

    for i, step in enumerate(steps):
        y = total_h - i * (box_h + gap)
        color = palette[i % len(palette)]
        rect = FancyBboxPatch((x0 - box_w / 2, y - box_h / 2),
                              box_w, box_h,
                              boxstyle="round,pad=0.08",
                              facecolor=color, edgecolor="white", linewidth=2)
        ax.add_patch(rect)
        ax.text(x0, y, step, ha="center", va="center",
                fontsize=11, color="white", fontweight="bold")
        if i < n - 1:
            arrow_y_start = y - box_h / 2
            arrow_y_end = y - box_h / 2 - gap
            ax.annotate("", xy=(x0, arrow_y_end + 0.02),
                        xytext=(x0, arrow_y_start - 0.02),
                        arrowprops=dict(arrowstyle="->", color=palette[0],
                                        lw=2.5))

    ax.set_xlim(0, 5)
    ax.set_ylim(-0.5, total_h + 0.5)
    return fig_to_stream(fig)


def make_timeline(events: list, palette: list, bg: str = "#FFFFFF") -> io.BytesIO:
    n = len(events)
    fig, ax = plt.subplots(figsize=(12, 3.5))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.axis("off")

    xs = np.linspace(0.5, 11.5, n)
    ax.plot([0.3, 11.7], [1, 1], color=palette[0], lw=3, zorder=1)

    for i, ev in enumerate(events):
        color = palette[i % len(palette)]
        ax.scatter(xs[i], 1, s=200, color=color, zorder=3, edgecolors="white", linewidths=2)
        va = "bottom" if i % 2 == 0 else "top"
        y_text = 1.18 if i % 2 == 0 else 0.82
        ax.text(xs[i], y_text, ev.get("date", ""), ha="center", va=va,
                fontsize=8.5, color=palette[0], fontweight="bold")
        y_ev = 1.38 if i % 2 == 0 else 0.62
        ax.text(xs[i], y_ev, ev.get("event", ""), ha="center", va=va,
                fontsize=9, color="#333333",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=color + "33"
                          if len(color) == 7 else "white", edgecolor="none"))

    ax.set_xlim(0, 12)
    ax.set_ylim(0.3, 1.7)
    return fig_to_stream(fig)


def make_pie(labels: list, values: list, palette: list, bg: str = "#FFFFFF") -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    colors = [palette[i % len(palette)] for i in range(len(labels))]
    wedge_props = dict(width=0.55, edgecolor="white", linewidth=2)
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors,
        autopct="%1.1f%%", startangle=140,
        wedgeprops=wedge_props, pctdistance=0.75
    )
    for t in texts:
        t.set_fontsize(10)
        t.set_color("#333333")
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("white")
        at.set_fontweight("bold")
    ax.set_title("", pad=10)
    return fig_to_stream(fig)


def make_bar(categories: list, series: list, palette: list, bg: str = "#FFFFFF") -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#CCCCCC")

    n_series = len(series)
    n_cats = len(categories)
    bar_w = 0.7 / max(n_series, 1)
    x = np.arange(n_cats)

    for i, s in enumerate(series):
        offset = (i - (n_series - 1) / 2) * bar_w
        bars = ax.bar(x + offset, s["values"], bar_w * 0.9,
                      label=s.get("name", f"Series {i+1}"),
                      color=palette[i % len(palette)],
                      edgecolor="white", linewidth=0.5)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + max(h * 0.01, 0.5),
                    f"{h:,.0f}", ha="center", va="bottom", fontsize=8, color="#555")

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.yaxis.set_tick_params(labelsize=9)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#EEEEEE", linewidth=0.8)
    if n_series > 1:
        ax.legend(fontsize=9, frameon=False)
    return fig_to_stream(fig)


def make_comparison(labels: list, criteria: list, values: list,
                    palette: list, bg: str = "#FFFFFF") -> io.BytesIO:
    n_crit = len(criteria)
    n_opts = len(labels)
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.set_xlim(0, 5.5)
    ax.set_ylim(-0.5, n_crit - 0.5)
    ax.set_yticks(range(n_crit))
    ax.set_yticklabels(criteria[::-1], fontsize=11)
    ax.xaxis.set_visible(False)

    bar_h = 0.3
    for i, (label, vals) in enumerate(zip(labels, values)):
        color = palette[i % len(palette)]
        for j, v in enumerate(vals):
            y = (n_crit - 1 - j) + (i - (n_opts - 1) / 2) * (bar_h + 0.05)
            ax.barh(y, v, bar_h, color=color, edgecolor="white", linewidth=0.5,
                    label=label if j == 0 else "")
            ax.text(v + 0.05, y, str(v), va="center", fontsize=9, color="#444")

    ax.legend(loc="lower right", fontsize=10, frameon=False)
    return fig_to_stream(fig)


def make_org_chart(root: str, children: list, palette: list, bg: str = "#FFFFFF") -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.axis("off")

    def draw_box(text, x, y, color, fontsize=10):
        rect = FancyBboxPatch((x - 1.1, y - 0.3), 2.2, 0.6,
                              boxstyle="round,pad=0.1",
                              facecolor=color, edgecolor="white", linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x, y, text, ha="center", va="center",
                fontsize=fontsize, color="white", fontweight="bold")

    draw_box(root, 6, 4.2, palette[0], fontsize=11)
    n = len(children)
    xs = np.linspace(1.5, 10.5, n) if n > 1 else [6.0]
    for i, child in enumerate(children):
        cx = xs[i]
        draw_box(child["name"], cx, 2.7, palette[1 % len(palette)])
        ax.annotate("", xy=(cx, 3.0), xytext=(6, 3.9),
                    arrowprops=dict(arrowstyle="-", color=palette[0], lw=1.5))
        sub = child.get("children", [])
        ns = len(sub)
        if ns:
            sub_xs = np.linspace(cx - 1.2 * (ns - 1) / 2,
                                 cx + 1.2 * (ns - 1) / 2, ns)
            for j, s in enumerate(sub):
                sx = sub_xs[j]
                label = s if isinstance(s, str) else s.get("name", str(s))
                draw_box(label, sx, 1.2, palette[2 % len(palette)], fontsize=9)
                ax.annotate("", xy=(sx, 1.5), xytext=(cx, 2.4),
                            arrowprops=dict(arrowstyle="-", color=palette[1], lw=1.2))

    ax.set_xlim(0, 12)
    ax.set_ylim(0.5, 5)
    return fig_to_stream(fig)


def render_diagram(slide_data: dict, theme: dict) -> io.BytesIO | None:
    palette = theme["mpl_palette"]
    bg = rgb_to_hex(theme["surface"])
    dtype = slide_data.get("diagram_type", "flowchart")
    data = slide_data.get("data", {})

    if dtype in ("flowchart", "process"):
        steps = data.get("steps", ["Step 1", "Step 2", "Step 3"])
        return make_flowchart(steps, palette, bg)
    elif dtype == "timeline":
        events = data.get("events", [])
        return make_timeline(events, palette, bg)
    elif dtype == "pie":
        return make_pie(data.get("labels", []), data.get("values", []), palette, bg)
    elif dtype == "bar":
        return make_bar(data.get("categories", []),
                        data.get("series", [{"name": "Value", "values": [1, 2, 3]}]),
                        palette, bg)
    elif dtype == "comparison":
        return make_comparison(data.get("labels", []),
                               data.get("criteria", []),
                               data.get("values", []),
                               palette, bg)
    elif dtype == "org_chart":
        return make_org_chart(data.get("root", "CEO"),
                              data.get("children", []),
                              palette, bg)
    return None


# ──────────────────────────────────────────────────────────────
# SLIDE BUILDERS
# ──────────────────────────────────────────────────────────────

def build_title_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["primary"])

    # Decorative accent bar bottom-left
    add_rect(slide, Inches(0), Inches(6.6), Inches(5), Inches(0.9), theme["accent"])
    # Subtle right panel
    add_rect(slide, Inches(8.5), Inches(0), Inches(4.83), SLIDE_H, theme["secondary"])

    # Title
    add_textbox(slide, slide_data.get("title", "Presentation"),
                Inches(0.7), Inches(2.0), Inches(7.5), Inches(1.8),
                font_size=40, bold=True, color=theme["text_light"],
                align=PP_ALIGN.LEFT)

    # Subtitle
    add_textbox(slide, slide_data.get("subtitle", ""),
                Inches(0.7), Inches(3.9), Inches(7.5), Inches(0.8),
                font_size=20, italic=True, color=theme["accent"],
                align=PP_ALIGN.LEFT)

    # Decorative icon-like circle on right panel
    circle = slide.shapes.add_shape(9, Inches(9.8), Inches(2.2), Inches(2.5), Inches(2.5))
    circle.fill.solid()
    circle.fill.fore_color.rgb = theme["primary"]
    circle.line.color.rgb = theme["accent"]
    circle.line.width = Pt(3)


def build_agenda_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["background"])

    # Header bar
    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.35), theme["primary"])
    add_textbox(slide, slide_data.get("title", "Agenda"),
                Inches(0.5), Inches(0.2), Inches(12), Inches(0.95),
                font_size=28, bold=True, color=theme["text_light"],
                align=PP_ALIGN.LEFT)

    items = slide_data.get("items", [])
    cols = 2 if len(items) > 4 else 1
    col_w = Inches(5.5) if cols == 2 else Inches(9)
    col_xs = [Inches(0.8), Inches(6.9)] if cols == 2 else [Inches(2.0)]

    per_col = math.ceil(len(items) / cols)
    for idx, item in enumerate(items):
        col = idx // per_col
        row = idx % per_col
        cx = col_xs[col] if col < len(col_xs) else col_xs[-1]
        cy = Inches(1.7 + row * 0.95)

        # Number badge
        badge = slide.shapes.add_shape(9, cx, cy + Inches(0.07),
                                       Inches(0.5), Inches(0.5))
        badge.fill.solid()
        badge.fill.fore_color.rgb = theme["secondary"]
        badge.line.fill.background()
        tf = badge.text_frame
        tf.paragraphs[0].text = str(idx + 1)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        run = tf.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.size = Pt(12)
        run.font.color.rgb = theme["text_light"]

        add_textbox(slide, item, cx + Inches(0.65), cy,
                    col_w - Inches(0.7), Inches(0.65),
                    font_size=15, color=theme["text_dark"],
                    align=PP_ALIGN.LEFT)

    # Accent bottom bar
    add_rect(slide, Inches(0), Inches(7.1), Inches(2), Inches(0.4), theme["accent"])


def build_content_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["surface"])

    # Left accent strip
    add_rect(slide, Inches(0), Inches(0), Inches(0.18), SLIDE_H, theme["secondary"])
    # Header
    add_rect(slide, Inches(0.18), Inches(0), Inches(13.15), Inches(1.35), theme["primary"])
    add_textbox(slide, slide_data.get("title", ""),
                Inches(0.5), Inches(0.2), Inches(12), Inches(0.95),
                font_size=26, bold=True, color=theme["text_light"],
                align=PP_ALIGN.LEFT)

    bullets = slide_data.get("bullets", [])
    for i, bullet in enumerate(bullets):
        y = Inches(1.65 + i * 0.88)
        # Bullet dot
        dot = slide.shapes.add_shape(9, Inches(0.5), y + Inches(0.18),
                                     Inches(0.18), Inches(0.18))
        dot.fill.solid()
        dot.fill.fore_color.rgb = theme["accent"]
        dot.line.fill.background()
        # Separator line
        line = slide.shapes.add_shape(1, Inches(0.5), y + Inches(0.72),
                                      Inches(12.3), Inches(0.02))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(0xE0, 0xE0, 0xE0)
        line.line.fill.background()
        add_textbox(slide, bullet,
                    Inches(0.85), y, Inches(12), Inches(0.75),
                    font_size=15, color=theme["text_dark"],
                    align=PP_ALIGN.LEFT)

    # Speaker notes
    notes = slide_data.get("speaker_notes", "")
    if notes:
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes


def build_diagram_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["surface"])

    # Header
    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.35), theme["primary"])
    add_textbox(slide, slide_data.get("title", ""),
                Inches(0.5), Inches(0.2), Inches(12), Inches(0.95),
                font_size=26, bold=True, color=theme["text_light"],
                align=PP_ALIGN.LEFT)

    img_stream = render_diagram(slide_data, theme)
    if img_stream:
        slide.shapes.add_picture(img_stream, Inches(0.5), Inches(1.5),
                                 Inches(12.33), Inches(5.7))
    else:
        desc = slide_data.get("description", "Diagram placeholder")
        add_textbox(slide, desc, Inches(1), Inches(2.5), Inches(11), Inches(3),
                    font_size=18, color=theme["text_dark"], align=PP_ALIGN.CENTER)

    notes = slide_data.get("speaker_notes", slide_data.get("description", ""))
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def build_stats_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["background"])

    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.35), theme["primary"])
    add_textbox(slide, slide_data.get("title", "Key Metrics"),
                Inches(0.5), Inches(0.2), Inches(12), Inches(0.95),
                font_size=26, bold=True, color=theme["text_light"],
                align=PP_ALIGN.LEFT)

    stats = slide_data.get("stats", [])
    n = len(stats)
    cols = min(n, 3)
    card_w = Inches(11.5 / cols)
    x_start = Inches((13.33 - 11.5) / 2)

    for i, stat in enumerate(stats):
        col = i % cols
        row = i // cols
        cx = x_start + col * card_w
        cy = Inches(1.6 + row * 2.7)

        # Card background
        add_rect(slide, cx + Inches(0.1), cy, card_w - Inches(0.2), Inches(2.4),
                 theme["surface"])
        # Top accent
        add_rect(slide, cx + Inches(0.1), cy, card_w - Inches(0.2), Inches(0.15),
                 theme["secondary"])

        add_textbox(slide, stat.get("value", ""),
                    cx + Inches(0.2), cy + Inches(0.2), card_w - Inches(0.4), Inches(1.0),
                    font_size=36, bold=True, color=theme["secondary"], align=PP_ALIGN.CENTER)
        add_textbox(slide, stat.get("label", ""),
                    cx + Inches(0.2), cy + Inches(1.1), card_w - Inches(0.4), Inches(0.5),
                    font_size=13, bold=True, color=theme["primary"], align=PP_ALIGN.CENTER)
        add_textbox(slide, stat.get("description", ""),
                    cx + Inches(0.2), cy + Inches(1.6), card_w - Inches(0.4), Inches(0.7),
                    font_size=11, italic=True, color=RGBColor(0x77, 0x77, 0x77),
                    align=PP_ALIGN.CENTER)


def build_quote_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["primary"])

    # Large decorative quote marks
    add_textbox(slide, "\u201C",
                Inches(0.4), Inches(0.5), Inches(2), Inches(2),
                font_size=120, bold=True, color=theme["accent"], align=PP_ALIGN.LEFT)

    add_textbox(slide, slide_data.get("quote", ""),
                Inches(1.2), Inches(1.5), Inches(10.5), Inches(3.5),
                font_size=24, italic=True, color=theme["text_light"],
                align=PP_ALIGN.CENTER)

    attr = slide_data.get("attribution", "")
    if attr:
        add_rect(slide, Inches(5.5), Inches(5.3), Inches(2.3), Inches(0.05),
                 theme["accent"])
        add_textbox(slide, f"\u2014 {attr}",
                    Inches(2), Inches(5.5), Inches(9.33), Inches(0.6),
                    font_size=14, bold=True, color=theme["accent"],
                    align=PP_ALIGN.CENTER)


def build_summary_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["background"])

    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.35), theme["secondary"])
    add_textbox(slide, slide_data.get("title", "Key Takeaways"),
                Inches(0.5), Inches(0.2), Inches(12), Inches(0.95),
                font_size=26, bold=True, color=theme["text_light"],
                align=PP_ALIGN.LEFT)

    bullets = slide_data.get("bullets", [])
    for i, bullet in enumerate(bullets):
        y = Inches(1.65 + i * 1.0)
        # Checkmark badge
        badge = slide.shapes.add_shape(9, Inches(0.5), y + Inches(0.1),
                                       Inches(0.55), Inches(0.55))
        badge.fill.solid()
        badge.fill.fore_color.rgb = theme["accent"]
        badge.line.fill.background()
        tf = badge.text_frame
        tf.paragraphs[0].text = "\u2713"
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        run = tf.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.size = Pt(14)
        run.font.color.rgb = theme["text_light"]

        add_textbox(slide, bullet, Inches(1.25), y,
                    Inches(11.5), Inches(0.75),
                    font_size=16, bold=True, color=theme["primary"],
                    align=PP_ALIGN.LEFT)


def build_closing_slide(prs, slide_data: dict, theme: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    set_slide_background(slide, theme["primary"])

    add_rect(slide, Inches(0), Inches(3.4), SLIDE_W, Inches(0.12), theme["accent"])
    add_rect(slide, Inches(0), Inches(0), Inches(0.4), SLIDE_H, theme["accent"])

    add_textbox(slide, slide_data.get("title", "Thank You"),
                Inches(1.0), Inches(1.5), Inches(11.33), Inches(1.4),
                font_size=52, bold=True, color=theme["text_light"],
                align=PP_ALIGN.CENTER)

    add_textbox(slide, slide_data.get("subtitle", "Questions & Discussion"),
                Inches(1.0), Inches(3.1), Inches(11.33), Inches(0.8),
                font_size=22, italic=True, color=theme["accent"],
                align=PP_ALIGN.CENTER)

    contact = slide_data.get("contact", "")
    if contact:
        add_textbox(slide, contact,
                    Inches(1.0), Inches(5.8), Inches(11.33), Inches(0.6),
                    font_size=14, color=theme["secondary"],
                    align=PP_ALIGN.CENTER)


# ──────────────────────────────────────────────────────────────
# SLIDE ROUTER
# ──────────────────────────────────────────────────────────────

BUILDERS = {
    "title":    build_title_slide,
    "agenda":   build_agenda_slide,
    "content":  build_content_slide,
    "diagram":  build_diagram_slide,
    "stats":    build_stats_slide,
    "quote":    build_quote_slide,
    "summary":  build_summary_slide,
    "closing":  build_closing_slide,
}


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:60]


def generate(plan_path: str):
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    theme_name = plan.get("theme", "corporate")
    theme = THEMES.get(theme_name, THEMES["corporate"])

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    slides = plan.get("slides", [])
    for slide_data in slides:
        slide_type = slide_data.get("type", "content")
        builder = BUILDERS.get(slide_type, build_content_slide)
        builder(prs, slide_data, theme)
        print(f"  ✓ [{slide_type}] {slide_data.get('title', '')}")

    output_name = slugify(plan.get("title", "presentation")) + ".pptx"
    prs.save(output_name)
    print(f"\n✅ Presentation saved: {output_name}")
    print(f"   Slides: {len(slides)}  |  Theme: {theme_name}")
    return output_name


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_presentation.py <slides_plan.json>")
        sys.exit(1)
    generate(sys.argv[1])
