#!/usr/bin/env python3
"""Snowflake Summit vendor dashboard builder.

Reads vendors.json, computes a transparent "Check-Out Score" for every partner
vendor, then writes a self-contained dashboard.html with KPIs, charts, a ranked
vendor table, and a "Must-See" highlight strip.

Usage:
    python build.py                 # uses ./vendors.json -> ./dashboard.html
    python build.py my_export.json  # use your own file (same schema)

Swap vendors.json for your authoritative partner-vendor export (matching the
field names documented in vendors.json `_meta.schema`) and re-run.
"""
import json
import sys
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Scoring model -----------------------------------------------------------
# Every component is normalized to 0..1, multiplied by its weight, and summed.
# Weights sum to 100, so the final score is a clean 0..100 "Check-Out Score".
# The model is deliberately simple and transparent so the ranking is defensible.
WEIGHTS = {
    "tier": 25,          # how much the vendor invested in the event (signal of seriousness/scale)
    "rating": 20,        # product quality, via G2-style review rating
    "integration": 15,   # depth of Snowflake integration (Native App)
    "ai": 15,            # AI/ML relevance — the dominant theme of the Summit
    "momentum": 15,      # company momentum proxy (funding / scale)
    "recognition": 10,   # Snowflake Partner-of-the-Year recognition
}

TIER_SCORE = {
    "Diamond": 1.00,
    "Platinum": 0.85,
    "Gold": 0.70,
    "Silver": 0.55,
    "Bronze": 0.40,
    "Exhibitor": 0.30,
}


def _momentum(funding_m, employees):
    """Momentum proxy on a 0..1 log scale. Public/large-cap (funding null) are
    treated as established (0.9). Otherwise blend funding and headcount."""
    import math
    if funding_m is None:
        return 0.90
    # ~$1B funding or ~2000 employees saturates to 1.0
    f = min(1.0, math.log10(max(funding_m, 1) + 1) / math.log10(1001))
    e = min(1.0, math.log10(max(employees or 1, 1) + 1) / math.log10(2001))
    return round(0.6 * f + 0.4 * e, 4)


def score_vendor(v):
    comp = {
        "tier": TIER_SCORE.get(v.get("tier"), 0.3),
        "rating": min(1.0, (v.get("g2_rating") or 0) / 5.0),
        "integration": 1.0 if v.get("native_app") else 0.35,
        "ai": 1.0 if v.get("ai_focus") else 0.30,
        "momentum": _momentum(v.get("funding_m"), v.get("employees")),
        "recognition": 1.0 if v.get("partner_of_year") else 0.0,
    }
    total = sum(comp[k] * WEIGHTS[k] for k in WEIGHTS)
    contributions = {k: round(comp[k] * WEIGHTS[k], 1) for k in WEIGHTS}
    return round(total, 1), contributions


def load(path):
    with open(path) as f:
        data = json.load(f)
    return data.get("vendors", data if isinstance(data, list) else [])


def build(src_path):
    vendors = load(src_path)
    for v in vendors:
        v["score"], v["score_breakdown"] = score_vendor(v)
    vendors.sort(key=lambda x: x["score"], reverse=True)
    for i, v in enumerate(vendors, 1):
        v["rank"] = i

    # "Hidden gems": strong product (rating >= 4.5) but lower sponsorship tier.
    for v in vendors:
        v["hidden_gem"] = (v.get("g2_rating") or 0) >= 4.5 and v.get("tier") in ("Silver", "Bronze", "Exhibitor")

    return vendors


# --- KPIs --------------------------------------------------------------------
def kpis(vendors):
    n = len(vendors)
    cats = {v["category"] for v in vendors}
    diamond_plat = sum(1 for v in vendors if v["tier"] in ("Diamond", "Platinum"))
    native = sum(1 for v in vendors if v.get("native_app"))
    ai = sum(1 for v in vendors if v.get("ai_focus"))
    poy = sum(1 for v in vendors if v.get("partner_of_year"))
    avg_rating = round(sum(v.get("g2_rating") or 0 for v in vendors) / n, 2) if n else 0
    avg_score = round(sum(v["score"] for v in vendors) / n, 1) if n else 0
    return [
        {"label": "Partner Vendors", "value": n, "sub": f"{len(cats)} categories"},
        {"label": "Diamond + Platinum", "value": diamond_plat, "sub": "top-tier sponsors"},
        {"label": "Snowflake Native Apps", "value": native, "sub": f"{round(100*native/n) if n else 0}% of floor"},
        {"label": "AI / ML Focused", "value": ai, "sub": f"{round(100*ai/n) if n else 0}% of vendors"},
        {"label": "Partners of the Year", "value": poy, "sub": "Snowflake-recognized"},
        {"label": "Avg Check-Out Score", "value": avg_score, "sub": f"avg rating {avg_rating}/5"},
    ]


def aggregate(vendors, key):
    out = {}
    for v in vendors:
        out[v[key]] = out.get(v[key], 0) + 1
    return out


def render(vendors, src_path):
    k = kpis(vendors)
    by_cat = aggregate(vendors, "category")
    by_tier = aggregate(vendors, "tier")
    tier_order = ["Diamond", "Platinum", "Gold", "Silver", "Bronze", "Exhibitor"]
    by_tier = {t: by_tier[t] for t in tier_order if t in by_tier}
    # avg score by category
    cat_scores = {}
    for c in by_cat:
        members = [v["score"] for v in vendors if v["category"] == c]
        cat_scores[c] = round(sum(members) / len(members), 1)

    top10 = vendors[:10]
    must_see = vendors[:6]
    gems = [v for v in vendors if v["hidden_gem"]][:5]

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": os.path.basename(src_path),
        "weights": WEIGHTS,
        "kpis": k,
        "by_cat": by_cat,
        "by_tier": by_tier,
        "cat_scores": cat_scores,
        "top10": top10,
        "must_see": must_see,
        "gems": gems,
        "vendors": vendors,
    }
    html = HTML_TEMPLATE.replace("/*__DATA__*/", json.dumps(payload))
    out_path = os.path.join(HERE, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(html)
    return out_path


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Snowflake Summit — Partner Vendor Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0b1020; --panel:#121a30; --panel2:#172241; --border:#243352;
    --text:#e8eeff; --muted:#8da2c8; --accent:#29b5e8; --accent2:#11567f;
    --good:#34d399; --warn:#fbbf24; --gem:#a78bfa;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:linear-gradient(180deg,#0b1020,#0d1426);color:var(--text)}
  header{padding:26px 28px 18px;border-bottom:1px solid var(--border);
         background:linear-gradient(120deg,#0e1730,#10243f)}
  .brand{display:flex;align-items:center;gap:12px}
  .logo{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,#29b5e8,#1b7fb8);
        display:flex;align-items:center;justify-content:center;font-weight:800;color:#06121f}
  h1{font-size:21px;margin:0;letter-spacing:.01em}
  .sub{color:var(--muted);font-size:13px;margin-top:4px}
  .wrap{max-width:1280px;margin:0 auto;padding:22px 24px 60px}
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:6px 0 26px}
  .kpi{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 15px}
  .kpi .v{font-size:26px;font-weight:800;color:#fff;line-height:1}
  .kpi .l{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-top:8px}
  .kpi .s{font-size:11px;color:var(--accent);margin-top:3px}
  .grid{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;margin-bottom:22px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:16px 18px}
  .card h3{margin:0 0 12px;font-size:14px;font-weight:700}
  .card h3 .hint{font-weight:400;color:var(--muted);font-size:12px;margin-left:6px}
  canvas{max-height:300px}
  .mustsee{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:8px}
  .ms{background:linear-gradient(160deg,#15233f,#101a30);border:1px solid var(--border);
      border-radius:12px;padding:14px;position:relative;overflow:hidden}
  .ms .rk{position:absolute;top:10px;right:12px;font-size:30px;font-weight:900;color:rgba(41,181,232,.18)}
  .ms .nm{font-size:15px;font-weight:700}
  .ms .ct{font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:.05em;margin:2px 0 6px}
  .ms .bl{font-size:12px;color:var(--muted);min-height:32px}
  .ms .sc{display:flex;align-items:baseline;gap:8px;margin-top:8px}
  .ms .sc b{font-size:24px;color:#fff}
  .ms .sc span{font-size:11px;color:var(--muted)}
  .badge{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;margin-right:5px;margin-top:6px;font-weight:600}
  .b-tier{background:rgba(41,181,232,.16);color:#7fd6f5}
  .b-poy{background:rgba(52,211,153,.16);color:var(--good)}
  .b-ai{background:rgba(167,139,250,.18);color:var(--gem)}
  .b-native{background:rgba(251,191,36,.15);color:var(--warn)}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--border)}
  th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;cursor:pointer;user-select:none}
  th:hover{color:var(--text)}
  tbody tr:hover{background:var(--panel2)}
  td.name{font-weight:600}
  td a{color:var(--accent);text-decoration:none}
  td a:hover{text-decoration:underline}
  .scorebar{display:inline-block;height:8px;border-radius:4px;background:linear-gradient(90deg,#1b7fb8,#29b5e8);vertical-align:middle;margin-right:8px}
  .pill{font-size:11px;padding:2px 8px;border-radius:20px;background:var(--panel2);border:1px solid var(--border)}
  .tier-Diamond{color:#bfe9ff}.tier-Platinum{color:#dde7ff}.tier-Gold{color:#ffd778}
  .tier-Silver{color:#cdd6e6}.tier-Bronze{color:#d8a47a}
  .gem-row td.name::after{content:" 💎";font-size:11px}
  .controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
  .controls input,.controls select{background:var(--panel2);border:1px solid var(--border);color:var(--text);
       border-radius:8px;padding:7px 10px;font-size:13px}
  .note{color:var(--muted);font-size:12px;margin-top:18px;line-height:1.5;border-top:1px solid var(--border);padding-top:14px}
  .modelbox{font-size:12px;color:var(--muted);line-height:1.6}
  .modelbox code{color:var(--accent)}
  @media(max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:1fr}.mustsee{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="logo">❄</div>
    <div>
      <h1>Snowflake Summit — Partner Vendor Dashboard</h1>
      <div class="sub" id="subhead"></div>
    </div>
  </div>
</header>
<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <h3 style="margin:6px 0 12px;font-size:15px">⭐ Must-See Vendors <span style="color:var(--muted);font-weight:400;font-size:12px">— highest Check-Out Score</span></h3>
  <div class="mustsee" id="mustsee"></div>

  <div class="grid" style="margin-top:22px">
    <div class="card"><h3>Top 10 by Check-Out Score</h3><canvas id="topChart"></canvas></div>
    <div class="card"><h3>Vendors by Sponsorship Tier</h3><canvas id="tierChart"></canvas></div>
  </div>
  <div class="grid">
    <div class="card"><h3>Vendors by Category</h3><canvas id="catChart"></canvas></div>
    <div class="card"><h3>Avg Score by Category <span class="hint">where is the strongest field?</span></h3><canvas id="catScoreChart"></canvas></div>
  </div>

  <div class="card">
    <h3>All Partner Vendors <span class="hint">click a column to sort · 💎 = hidden gem</span></h3>
    <div class="controls">
      <input id="search" placeholder="Search vendor / category…" style="flex:1;min-width:200px"/>
      <select id="catFilter"><option value="">All categories</option></select>
      <select id="tierFilter"><option value="">All tiers</option></select>
    </div>
    <table id="vtable">
      <thead><tr>
        <th data-k="rank">#</th><th data-k="name">Vendor</th><th data-k="category">Category</th>
        <th data-k="tier">Tier</th><th data-k="booth">Booth</th><th data-k="g2_rating">Rating</th>
        <th data-k="score">Check-Out Score</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="card" style="margin-top:16px">
    <h3>How the Check-Out Score works</h3>
    <div class="modelbox" id="model"></div>
  </div>

  <div class="note" id="note"></div>
</div>

<script>
const DATA = /*__DATA__*/;
const fmt = n => (n===null||n===undefined)?"—":n;

// subhead
document.getElementById('subhead').textContent =
  `${DATA.vendors.length} partner vendors · source: ${DATA.source} · generated ${DATA.generated}`;

// KPIs
document.getElementById('kpis').innerHTML = DATA.kpis.map(k=>
  `<div class="kpi"><div class="v">${k.value}</div><div class="l">${k.label}</div><div class="s">${k.sub}</div></div>`).join('');

// Must-see cards
document.getElementById('mustsee').innerHTML = DATA.must_see.map(v=>{
  const badges = [
    `<span class="badge b-tier">${v.tier}</span>`,
    v.partner_of_year?`<span class="badge b-poy">Partner of Year</span>`:'',
    v.ai_focus?`<span class="badge b-ai">AI</span>`:'',
    v.native_app?`<span class="badge b-native">Native App</span>`:''
  ].join('');
  return `<div class="ms"><div class="rk">${v.rank}</div>
    <div class="nm">${v.name}</div><div class="ct">${v.category}</div>
    <div class="bl">${v.blurb||''}</div>
    <div>${badges}</div>
    <div class="sc"><b>${v.score}</b><span>/ 100 · booth ${fmt(v.booth)}</span></div></div>`;
}).join('');

// Model explanation
const w = DATA.weights;
document.getElementById('model').innerHTML =
  `Each vendor earns a <b>Check-Out Score (0–100)</b> by combining six normalized signals:<br><br>` +
  `• <code>Sponsorship tier</code> (${w.tier} pts) — investment / scale at the event<br>` +
  `• <code>Product rating</code> (${w.rating} pts) — G2-style review score ÷ 5<br>` +
  `• <code>Snowflake integration</code> (${w.integration} pts) — full points for a Native App<br>` +
  `• <code>AI / ML focus</code> (${w.ai} pts) — the dominant Summit theme<br>` +
  `• <code>Company momentum</code> (${w.momentum} pts) — log-scaled funding + headcount<br>` +
  `• <code>Partner-of-the-Year</code> (${w.recognition} pts) — Snowflake recognition<br><br>` +
  `Weights sum to 100. "💎 Hidden gems" are vendors rated ≥4.5 sitting at Silver/Bronze tier — strong product, smaller booth, easy to miss.`;

// Charts
const C = {grid:'#243352', tick:'#8da2c8'};
const baseOpts = {plugins:{legend:{labels:{color:C.tick}}},
  scales:{x:{ticks:{color:C.tick},grid:{color:C.grid}},y:{ticks:{color:C.tick},grid:{color:C.grid}}}};

new Chart(document.getElementById('topChart'),{type:'bar',
  data:{labels:DATA.top10.map(v=>v.name),
    datasets:[{label:'Check-Out Score',data:DATA.top10.map(v=>v.score),
      backgroundColor:'#29b5e8'}]},
  options:{...baseOpts,indexAxis:'y',plugins:{legend:{display:false}},
    scales:{x:{min:0,max:100,ticks:{color:C.tick},grid:{color:C.grid}},y:{ticks:{color:C.tick},grid:{display:false}}}}});

new Chart(document.getElementById('tierChart'),{type:'doughnut',
  data:{labels:Object.keys(DATA.by_tier),
    datasets:[{data:Object.values(DATA.by_tier),
      backgroundColor:['#bfe9ff','#7fb8e8','#ffd778','#cdd6e6','#d8a47a','#5b6a85']}]},
  options:{plugins:{legend:{position:'right',labels:{color:C.tick}}}}});

new Chart(document.getElementById('catChart'),{type:'bar',
  data:{labels:Object.keys(DATA.by_cat),
    datasets:[{label:'Vendors',data:Object.values(DATA.by_cat),backgroundColor:'#11567f'}]},
  options:{...baseOpts,plugins:{legend:{display:false}}}});

const cs = DATA.cat_scores;
new Chart(document.getElementById('catScoreChart'),{type:'bar',
  data:{labels:Object.keys(cs),datasets:[{label:'Avg score',data:Object.values(cs),backgroundColor:'#a78bfa'}]},
  options:{...baseOpts,plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:C.tick},grid:{display:false}},y:{min:0,max:100,ticks:{color:C.tick},grid:{color:C.grid}}}}});

// Table
const tbody = document.querySelector('#vtable tbody');
const catSel = document.getElementById('catFilter'), tierSel=document.getElementById('tierFilter');
[...new Set(DATA.vendors.map(v=>v.category))].sort().forEach(c=>catSel.add(new Option(c,c)));
[...new Set(DATA.vendors.map(v=>v.tier))].forEach(t=>tierSel.add(new Option(t,t)));
let sortK='rank', sortAsc=true, rows=[...DATA.vendors];
const maxScore = Math.max(...DATA.vendors.map(v=>v.score));

function draw(){
  const q=document.getElementById('search').value.toLowerCase();
  const cf=catSel.value, tf=tierSel.value;
  let r=rows.filter(v=>(!q||v.name.toLowerCase().includes(q)||v.category.toLowerCase().includes(q))
    &&(!cf||v.category===cf)&&(!tf||v.tier===tf));
  r.sort((a,b)=>{let x=a[sortK],y=b[sortK];
    if(typeof x==='string'){x=x.toLowerCase();y=(y||'').toLowerCase();}
    return (x>y?1:x<y?-1:0)*(sortAsc?1:-1);});
  tbody.innerHTML=r.map(v=>{
    const wpx=Math.round((v.score/maxScore)*70)+10;
    return `<tr class="${v.hidden_gem?'gem-row':''}">
      <td>${v.rank}</td>
      <td class="name"><a href="${v.website}" target="_blank" rel="noopener">${v.name}</a></td>
      <td>${v.category}</td>
      <td><span class="pill tier-${v.tier}">${v.tier}</span></td>
      <td>${fmt(v.booth)}</td>
      <td>${fmt(v.g2_rating)}</td>
      <td><span class="scorebar" style="width:${wpx}px"></span><b>${v.score}</b></td>
    </tr>`;}).join('');
}
document.querySelectorAll('#vtable th').forEach(th=>th.onclick=()=>{
  const k=th.dataset.k; if(sortK===k)sortAsc=!sortAsc;else{sortK=k;sortAsc=(k==='rank'||k==='name'||k==='category');}
  draw();});
['input','change'].forEach(e=>{document.getElementById('search').addEventListener(e,draw);
  catSel.addEventListener(e,draw);tierSel.addEventListener(e,draw);});
draw();

document.getElementById('note').innerHTML =
  `<b>Data note:</b> this dashboard was seeded with real Snowflake-ecosystem partner companies, but per-vendor attributes ` +
  `(tier, booth, funding, rating) are approximate starter values. Replace <code>vendors.json</code> with your authoritative ` +
  `partner-vendor export (same field names) and re-run <code>python build.py</code> to regenerate. Scoring is a heuristic ` +
  `aid for prioritizing booths — not an endorsement.`;
</script>
</body>
</html>
"""


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "vendors.json")
    vendors = build(src)
    out = render(vendors, src)
    print(f"Scored {len(vendors)} vendors -> {out}")
    print("Top 5:")
    for v in vendors[:5]:
        print(f"  {v['rank']:>2}. {v['name']:<16} {v['score']:>5}  [{v['tier']}, {v['category']}]")


if __name__ == "__main__":
    main()
