# Snowflake Summit — Partner Vendor Dashboard

A self-contained dashboard that turns a list of Snowflake Summit partner vendors
into KPIs, charts, and a ranked **"Check-Out Score"** so you can quickly decide
which booths are worth your time.

## Quick start

```bash
cd snowflake_summit
python3 build.py            # reads vendors.json -> writes dashboard.html
open dashboard.html         # (macOS) or just double-click it
```

`dashboard.html` is fully self-contained — all data is inlined at build time.
The only runtime dependency is Chart.js, pulled from a CDN, so the charts need
an internet connection when you open the page.

## Use your own vendor file

The seeded `vendors.json` is **illustrative starter data**: the companies are
real Snowflake-ecosystem partners, but per-vendor attributes (tier, booth,
funding, rating) are approximate. Swap in your authoritative export and rebuild:

```bash
python3 build.py path/to/your_vendors.json
```

Your file should be JSON shaped like `vendors.json` — either a top-level
`{"vendors": [...]}` object or a bare list. Each vendor supports these fields
(missing ones degrade gracefully):

| field | type | used for |
|-------|------|----------|
| `name` | string | label |
| `category` | string | category charts / filters |
| `tier` | Diamond/Platinum/Gold/Silver/Bronze/Exhibitor | tier chart + 25% of score |
| `booth` | string | display |
| `website` | url | link |
| `g2_rating` | 0–5 | 20% of score |
| `native_app` | bool | 15% of score |
| `ai_focus` | bool | 15% of score |
| `funding_m` | number or null | momentum (15% of score) |
| `employees` | number | momentum |
| `partner_of_year` | bool | 10% of score |
| `blurb` | string | card description |

If you have a CSV/XLSX instead of JSON, convert it first (e.g. with `pandas`)
and keep these column names.

## The Check-Out Score (0–100)

A transparent weighted blend of six normalized signals — see the exact weights
in `build.py` (`WEIGHTS`) and the in-page "How the Check-Out Score works" panel:

- **Sponsorship tier** (25) — how much the vendor invested in the event
- **Product rating** (20) — G2-style review score ÷ 5
- **Snowflake integration** (15) — full points for a Native App
- **AI / ML focus** (15) — the dominant Summit theme
- **Company momentum** (15) — log-scaled funding + headcount
- **Partner of the Year** (10) — Snowflake recognition

The dashboard highlights the **top 6 "Must-See" vendors** by score and flags
**💎 hidden gems** — vendors rated ≥4.5 sitting at a smaller (Silver/Bronze)
booth that are easy to walk past.

Tune the model by editing `WEIGHTS` and `TIER_SCORE` in `build.py`, then rerun.

> The score is a prioritization heuristic, not an endorsement.
