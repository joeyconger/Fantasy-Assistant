"""Shared design system for the web dashboard: CSS tokens + small HTML-
generating helpers (position badges, avatars, tabs, stat tiles). Hand-rolled
CSS rather than a component library (e.g. shadcn/ui) — see the conversation
that decided this: adopting a React-based library would mean a full
Node/SPA rewrite of an app that's otherwise a simple Python server-rendered
tool with no complex client state, which isn't worth the migration risk for
what these pages actually need.

Color system: positions get consistent colors everywhere a player appears
(QB/RB/WR/TE/K/DEF), and league formats (redraft/dynasty/devy) get their
own distinct palette so the two color scales are never confused with each
other. Supports light and dark (prefers-color-scheme) since this may get
checked on a phone at odd hours during waivers.

Visual style is deliberately Sleeper-app-flavored (teal/violet gradient
accent, dark-leaning surfaces, glossy cards) per an explicit request to
make this "look like a sleek modern fantasy app" rather than a styled
document — badges/avatars use a computed gradient (flat color -> a darker
shade of itself, _darken()) instead of a flat fill, cards/buttons/nav pills
get shadow + hover-lift transitions, and the header is a sticky, blurred
app-bar instead of static page content. All CSS-only except the existing
Sync-button disable-on-submit script in web.py and native <details>
disclosure widgets for collapsible sections — no client-state framework.
"""

from __future__ import annotations

import html

POSITION_COLORS = {
    "QB": "#8b5cf6",  # violet
    "RB": "#22c55e",  # green
    "WR": "#3b82f6",  # blue
    "TE": "#f97316",  # orange
    "K": "#64748b",  # slate
    "DEF": "#ef4444",  # red
    "D/ST": "#ef4444",
}
DEFAULT_POSITION_COLOR = "#94a3b8"

FORMAT_COLORS = {
    "redraft": "#0ea5e9",  # sky
    "dynasty": "#a855f7",  # purple
    "devy": "#14b8a6",  # teal
}
DEFAULT_FORMAT_COLOR = "#94a3b8"


def _darken(hex_color: str, factor: float = 0.62) -> str:
    """Darkens a #rrggbb color by `factor` (0-1, lower = darker) — used to
    build a two-stop gradient from a single flat color (badges/avatars),
    computed here rather than via CSS color-mix() so it doesn't depend on
    per-element custom properties or browser support for that function."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return hex_color
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def gradient(hex_color: str) -> str:
    return f"linear-gradient(135deg, {hex_color}, {_darken(hex_color)})"


PAGE_STYLE = """
:root {
  --bg: #f3f5fb;
  --surface: #ffffff;
  --surface-2: #eceffa;
  --text: #0f1729;
  --muted: #64748b;
  --border: #e3e7f2;
  --accent: #0ea5a0;
  --accent-2: #6366f1;
  --accent-text: #ffffff;
  --buy: #16a34a;
  --sell: #dc2626;
  --radius: 14px;
  --radius-sm: 10px;
  --space-1: 0.375rem;
  --space-2: 0.75rem;
  --space-3: 1.25rem;
  --space-4: 2rem;
  --shadow: 0 1px 2px rgba(15,23,42,0.05), 0 8px 20px -12px rgba(15,23,42,0.15);
  --shadow-hover: 0 4px 10px rgba(15,23,42,0.08), 0 18px 32px -14px rgba(15,23,42,0.22);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #080b14;
    --surface: #121a2c;
    --surface-2: #1a2338;
    --text: #f1f5fb;
    --muted: #8b93ab;
    --border: #232c46;
    --accent: #2dd4c8;
    --accent-2: #818cf8;
    --accent-text: #06120f;
    --buy: #4ade80;
    --sell: #f87171;
    --shadow: 0 1px 2px rgba(0,0,0,0.35), 0 8px 20px -12px rgba(0,0,0,0.55);
    --shadow-hover: 0 4px 12px rgba(0,0,0,0.45), 0 20px 36px -16px rgba(0,0,0,0.65);
  }
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  max-width: 1000px;
  margin: 0 auto;
  padding: 0 var(--space-2) var(--space-4);
  line-height: 1.45;
  animation: fade-in 0.25s ease-out;
}
@keyframes fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
@keyframes pulse { 0%, 100% { opacity: 0.65; } 50% { opacity: 0.9; } }

.app-bar {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: var(--space-2) 0 var(--space-1);
  margin: 0 0 var(--space-3);
}
h1 { font-size: 1.4rem; margin: 0 0 var(--space-2); letter-spacing: -0.01em; }
h2 { font-size: 1.15rem; margin: var(--space-4) 0 var(--space-2); letter-spacing: -0.01em; }
h3 { font-size: 1rem; margin: 0 0 var(--space-1); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

nav { display: flex; gap: var(--space-2); flex-wrap: wrap; overflow-x: auto; padding-bottom: 2px; }
nav a { font-size: 0.85rem; font-weight: 700; padding: 0.4rem 0.85rem;
        border-radius: 999px; background: var(--surface); border: 1px solid var(--border);
        white-space: nowrap; box-shadow: var(--shadow); transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease; }
nav a:hover { text-decoration: none; border-color: var(--accent); transform: translateY(-1px); box-shadow: var(--shadow-hover); }
nav a.active { color: var(--accent-text); border-color: transparent; box-shadow: var(--shadow-hover);
                background: linear-gradient(135deg, var(--accent), var(--accent-2)); }

.tag { font-size: 0.75rem; font-weight: normal; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; padding: var(--space-2) 0; }
.errors { background: color-mix(in srgb, var(--sell) 12%, var(--surface));
          border: 1px solid var(--sell); padding: var(--space-2) var(--space-3);
          border-radius: var(--radius); margin-bottom: var(--space-2); }

button, .btn {
  padding: 0.55rem 1.1rem; cursor: pointer; font-size: 0.9rem; font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: var(--accent-text); border: none; border-radius: var(--radius-sm);
  box-shadow: var(--shadow); transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
}
button:hover:not(:disabled) { transform: translateY(-1px); box-shadow: var(--shadow-hover); }
button:active:not(:disabled) { transform: translateY(0); }
button:disabled { opacity: 0.65; cursor: wait; animation: pulse 1.3s ease-in-out infinite; }

.table-wrap { overflow-x: auto; margin-bottom: var(--space-3); border-radius: var(--radius);
              border: 1px solid var(--border); box-shadow: var(--shadow); }
table { border-collapse: collapse; width: 100%; background: var(--surface); }
th, td { text-align: left; padding: var(--space-1) var(--space-2); border-bottom: 1px solid var(--border);
         white-space: nowrap; font-size: 0.9rem; }
th { background: var(--surface-2); color: var(--muted); font-weight: 700; font-size: 0.75rem;
     text-transform: uppercase; letter-spacing: 0.04em; }
tbody tr { transition: background 0.12s ease; }
tbody tr:hover { background: var(--surface-2); }
tbody tr:last-child td { border-bottom: none; }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
        padding: var(--space-3); margin-bottom: var(--space-2); box-shadow: var(--shadow);
        transition: transform 0.15s ease, box-shadow 0.15s ease; }
.card:hover { transform: translateY(-2px); box-shadow: var(--shadow-hover); }

.badge { display: inline-flex; align-items: center; padding: 0.15rem 0.55rem; border-radius: 999px;
         font-size: 0.7rem; font-weight: 700; color: #fff; white-space: nowrap;
         box-shadow: 0 1px 4px rgba(0,0,0,0.2); letter-spacing: 0.02em; }

.avatar { display: inline-flex; align-items: center; justify-content: center; width: 1.85rem; height: 1.85rem;
          border-radius: 50%; color: #fff; font-size: 0.7rem; font-weight: 700; flex-shrink: 0;
          box-shadow: 0 2px 6px rgba(0,0,0,0.2); }

.player-cell { display: flex; align-items: center; gap: var(--space-1); }
.player-name { font-weight: 600; }

.tabs { display: flex; gap: var(--space-1); flex-wrap: wrap; margin-bottom: var(--space-3); }
.tabs a { padding: 0.4rem 0.85rem; border-radius: 999px; font-size: 0.85rem; font-weight: 700;
          border: 1px solid var(--border); background: var(--surface); color: var(--text);
          box-shadow: var(--shadow); transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease; }
.tabs a:hover { text-decoration: none; transform: translateY(-1px); box-shadow: var(--shadow-hover); border-color: var(--accent); }
.tabs a.active { color: var(--accent-text); border-color: transparent; box-shadow: var(--shadow-hover); }

.stat-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
              gap: var(--space-2); margin-bottom: var(--space-3); }
.stat-tile { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
             padding: var(--space-3); box-shadow: var(--shadow); position: relative; overflow: hidden; }
.stat-tile::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
                      background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
.stat-tile .value { font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em; }
.stat-tile .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 0.15rem; }

.flag-buy, .flag-sell { font-weight: 700; }
.flag-buy { color: var(--buy); }
.flag-sell { color: var(--sell); }
.flag-buy::before, .flag-sell::before { content: "●"; margin-right: 0.35em; font-size: 0.65em; vertical-align: middle; }

details.collapsible { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
                       box-shadow: var(--shadow); margin-bottom: var(--space-2); padding: var(--space-2) var(--space-3); }
details.collapsible summary { cursor: pointer; list-style: none; display: flex; align-items: center;
                               justify-content: space-between; gap: var(--space-2); font-weight: 600; }
details.collapsible summary::-webkit-details-marker { display: none; }
details.collapsible summary::after { content: "⌄"; color: var(--muted); font-size: 1.1rem;
                                      transition: transform 0.15s ease; }
details.collapsible[open] summary::after { transform: rotate(180deg); }
details.collapsible .table-wrap { margin-top: var(--space-2); margin-bottom: 0; }

@media (max-width: 640px) {
  body { padding: 0 var(--space-1) var(--space-4); }
  h1 { font-size: 1.2rem; }
  th, td { font-size: 0.82rem; padding: var(--space-1); }
}
"""


def position_badge(position: str | None) -> str:
    if not position:
        return ""
    color = POSITION_COLORS.get(position, DEFAULT_POSITION_COLOR)
    return f'<span class="badge" style="background:{gradient(color)};">{html.escape(position)}</span>'


def format_badge(format_: str | None) -> str:
    if not format_:
        return ""
    color = FORMAT_COLORS.get(format_, DEFAULT_FORMAT_COLOR)
    return f'<span class="badge" style="background:{gradient(color)};">{html.escape(format_)}</span>'


def avatar(name: str, position: str | None = None) -> str:
    """Initials-based avatar (no headshot source available), colored by
    position for a quick visual read of what a player is at a glance."""
    initials = "".join(part[0] for part in (name or "?").split()[:2]).upper() or "?"
    color = POSITION_COLORS.get(position, DEFAULT_POSITION_COLOR) if position else DEFAULT_POSITION_COLOR
    return f'<span class="avatar" style="background-image:{gradient(color)};">{html.escape(initials)}</span>'


def player_cell(name: str, position: str | None = None) -> str:
    return (
        f'<span class="player-cell">{avatar(name, position)}'
        f'<span class="player-name">{html.escape(name)}</span>{position_badge(position)}</span>'
    )


def stat_tile(label: str, value: str) -> str:
    return f'<div class="stat-tile"><div class="value">{html.escape(str(value))}</div><div class="label">{html.escape(label)}</div></div>'


def table_wrap(inner_table_html: str) -> str:
    return f'<div class="table-wrap">{inner_table_html}</div>'


def collapsible(summary_html: str, inner_html: str, open_: bool = True) -> str:
    """Native <details>/<summary> disclosure widget, styled to match the
    rest of the design system — zero JS, works everywhere, gives sections
    (e.g. per-league standings) a real collapse/expand interaction."""
    open_attr = " open" if open_ else ""
    return f'<details class="collapsible"{open_attr}><summary>{summary_html}</summary>{inner_html}</details>'
