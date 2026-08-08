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

PAGE_STYLE = """
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --accent: #2563eb;
  --accent-text: #ffffff;
  --buy: #16a34a;
  --sell: #dc2626;
  --radius: 10px;
  --space-1: 0.375rem;
  --space-2: 0.75rem;
  --space-3: 1.25rem;
  --space-4: 2rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b1220;
    --surface: #151f32;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --border: #263349;
    --accent: #3b82f6;
    --accent-text: #ffffff;
    --buy: #4ade80;
    --sell: #f87171;
  }
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  max-width: 960px;
  margin: 0 auto;
  padding: var(--space-3) var(--space-2) var(--space-4);
  line-height: 1.45;
}
h1 { font-size: 1.5rem; margin: 0 0 var(--space-2); }
h2 { font-size: 1.15rem; margin: var(--space-4) 0 var(--space-2); }
h3 { font-size: 1rem; margin: 0 0 var(--space-1); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

nav { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-3);
      overflow-x: auto; padding-bottom: var(--space-1); }
nav a { font-size: 0.9rem; font-weight: 600; padding: var(--space-1) var(--space-2);
        border-radius: 999px; background: var(--surface); border: 1px solid var(--border);
        white-space: nowrap; }
nav a:hover { text-decoration: none; border-color: var(--accent); }

.tag { font-size: 0.75rem; font-weight: normal; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; padding: var(--space-2) 0; }
.errors { background: color-mix(in srgb, var(--sell) 12%, var(--surface));
          border: 1px solid var(--sell); padding: var(--space-2) var(--space-3);
          border-radius: var(--radius); margin-bottom: var(--space-2); }

button, .btn {
  padding: var(--space-1) var(--space-3); cursor: pointer; font-size: 0.9rem; font-weight: 600;
  background: var(--accent); color: var(--accent-text); border: none; border-radius: var(--radius);
}
button:disabled { opacity: 0.6; cursor: wait; }

.table-wrap { overflow-x: auto; margin-bottom: var(--space-3); border-radius: var(--radius);
              border: 1px solid var(--border); }
table { border-collapse: collapse; width: 100%; background: var(--surface); }
th, td { text-align: left; padding: var(--space-1) var(--space-2); border-bottom: 1px solid var(--border);
         white-space: nowrap; font-size: 0.9rem; }
th { color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }
tbody tr:last-child td { border-bottom: none; }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
        padding: var(--space-3); margin-bottom: var(--space-2); }

.badge { display: inline-flex; align-items: center; padding: 0.15rem 0.5rem; border-radius: 999px;
         font-size: 0.72rem; font-weight: 700; color: #fff; white-space: nowrap; }

.avatar { display: inline-flex; align-items: center; justify-content: center; width: 1.75rem; height: 1.75rem;
          border-radius: 50%; color: #fff; font-size: 0.7rem; font-weight: 700; flex-shrink: 0; }

.player-cell { display: flex; align-items: center; gap: var(--space-1); }
.player-name { font-weight: 600; }

.tabs { display: flex; gap: var(--space-1); flex-wrap: wrap; margin-bottom: var(--space-3); }
.tabs a { padding: var(--space-1) var(--space-2); border-radius: 999px; font-size: 0.85rem; font-weight: 600;
          border: 1px solid var(--border); background: var(--surface); color: var(--text); }
.tabs a:hover { text-decoration: none; }
.tabs a.active { color: #fff; border-color: transparent; }

.stat-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
              gap: var(--space-2); margin-bottom: var(--space-3); }
.stat-tile { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
             padding: var(--space-2) var(--space-3); }
.stat-tile .value { font-size: 1.4rem; font-weight: 700; }
.stat-tile .label { font-size: 0.78rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }

.flag-buy { color: var(--buy); font-weight: 700; }
.flag-sell { color: var(--sell); font-weight: 700; }

@media (max-width: 640px) {
  body { padding: var(--space-2) var(--space-1) var(--space-4); }
  h1 { font-size: 1.25rem; }
  th, td { font-size: 0.82rem; padding: var(--space-1); }
}
"""


def position_badge(position: str | None) -> str:
    if not position:
        return ""
    color = POSITION_COLORS.get(position, DEFAULT_POSITION_COLOR)
    return f'<span class="badge" style="background:{color};">{html.escape(position)}</span>'


def format_badge(format_: str | None) -> str:
    if not format_:
        return ""
    color = FORMAT_COLORS.get(format_, DEFAULT_FORMAT_COLOR)
    return f'<span class="badge" style="background:{color};">{html.escape(format_)}</span>'


def avatar(name: str, position: str | None = None) -> str:
    """Initials-based avatar (no headshot source available), colored by
    position for a quick visual read of what a player is at a glance."""
    initials = "".join(part[0] for part in (name or "?").split()[:2]).upper() or "?"
    color = POSITION_COLORS.get(position, DEFAULT_POSITION_COLOR) if position else DEFAULT_POSITION_COLOR
    return f'<span class="avatar" style="background:{color};">{html.escape(initials)}</span>'


def player_cell(name: str, position: str | None = None) -> str:
    return (
        f'<span class="player-cell">{avatar(name, position)}'
        f'<span class="player-name">{html.escape(name)}</span>{position_badge(position)}</span>'
    )


def stat_tile(label: str, value: str) -> str:
    return f'<div class="stat-tile"><div class="value">{html.escape(str(value))}</div><div class="label">{html.escape(label)}</div></div>'


def table_wrap(inner_table_html: str) -> str:
    return f'<div class="table-wrap">{inner_table_html}</div>'
