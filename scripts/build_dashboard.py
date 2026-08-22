"""
Genera docs/index.html a partire da data/prices_history.json,
data/compatibility.json e acquistati.json (componenti già comprati,
mostrati con prezzo fisso e badge "Acquistato").
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "data" / "prices_history.json"
COMPAT_FILE = ROOT / "data" / "compatibility.json"
ACQUISTATI_FILE = ROOT / "acquistati.json"
OUTPUT_FILE = ROOT / "docs" / "index.html"

TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitor Prezzi PC</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f1115;
    color: #e8e8e8;
    margin: 0;
    padding: 24px 16px;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitle {{ color: #999; font-size: 0.85rem; margin-bottom: 24px; }}
  .card {{
    background: #1a1d24;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }}
  .card h2 {{ font-size: 1.1rem; margin: 0 0 4px 0; }}
  .price-now {{ font-size: 1.8rem; font-weight: 700; color: #4ade80; margin: 4px 0; }}
  .price-meta {{ font-size: 0.8rem; color: #888; margin-bottom: 4px; }}
  .price-link {{ font-size: 0.8rem; color: #60a5fa; text-decoration: none; }}
  .price-link:hover {{ text-decoration: underline; }}
  .no-data {{ color: #888; font-style: italic; }}
  canvas {{ max-height: 220px; cursor: pointer; }}
  .chart-hint {{ font-size: 0.7rem; color: #666; margin-top: 4px; }}
  .compat-ok {{ color: #4ade80; }}
  .compat-ko {{ color: #f87171; }}
  .compat-riga {{ font-size: 0.85rem; margin-bottom: 8px; line-height: 1.4; }}
  .compat-nota {{ font-size: 0.75rem; color: #888; margin-top: 12px; font-style: italic; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
  .badge-ok {{ background: rgba(74,222,128,0.15); color: #4ade80; }}
  .badge-ko {{ background: rgba(248,113,113,0.15); color: #f87171; }}
  .badge-acquistato {{ background: rgba(96,165,250,0.15); color: #60a5fa; }}
  .total-card {{
    background: linear-gradient(135deg, #1a1d24, #232733);
    border: 1px solid #2a2d35;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    text-align: center;
  }}
  .total-label {{ font-size: 0.9rem; color: #999; margin-bottom: 4px; }}
  .total-value {{ font-size: 2.4rem; font-weight: 800; color: #4ade80; }}
  .total-meta {{ font-size: 0.75rem; color: #666; margin-top: 4px; }}
  .section-label {{ font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; margin: 20px 0 10px 0; }}
</style>
</head>
<body>
  <h1>💻 Monitor Prezzi Componenti PC</h1>
  <div class="subtitle">Ultimo aggiornamento: {last_update}</div>
  {total_html}
  {compat_html}
  {acquistati_html}
  {cards}
  <script>
    const chartData = {chart_data_json};
    Object.entries(chartData).forEach(([id, d]) => {{
      const ctx = document.getElementById('chart_' + id);
      if (!ctx) return;
      const chart = new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: d.labels,
          datasets: [{{
            label: 'Prezzo (EUR)',
            data: d.prices,
            borderColor: '#4ade80',
            backgroundColor: 'rgba(74,222,128,0.1)',
            tension: 0.2,
            fill: true,
            pointRadius: 5,
            pointHoverRadius: 8,
          }}]
        }},
        options: {{
          responsive: true,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                label: function(ctx) {{
                  const url = d.urls[ctx.dataIndex];
                  return url ? 'Prezzo: € ' + ctx.parsed.y + '  (clicca per aprire l\\'offerta)' : 'Prezzo: € ' + ctx.parsed.y;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{ ticks: {{ color: '#888' }}, grid: {{ color: '#2a2d35' }} }},
            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: '#2a2d35' }} }}
          }},
          onClick: function(evt, elements) {{
            if (elements.length > 0) {{
              const idx = elements[0].index;
              const url = d.urls[idx];
              if (url) window.open(url, '_blank');
            }}
          }},
          onHover: function(evt, elements) {{
            evt.native.target.style.cursor = elements.length > 0 ? 'pointer' : 'default';
          }}
        }}
      }});
    }});
  </script>
</body>
</html>
"""

CARD_TEMPLATE = """
<div class="card">
  <h2>{nome}</h2>
  {price_html}
  <canvas id="chart_{id}"></canvas>
  <div class="chart-hint">👆 clicca un punto del grafico per aprire l'offerta corrispondente</div>
</div>
"""

ACQUISTATO_CARD_TEMPLATE = """
<div class="card">
  <h2>{nome} <span class="badge badge-acquistato">✅ Acquistato</span></h2>
  <div class="price-now">{prezzo:.2f} €</div>
  <div class="price-meta">Prezzo fisso di acquisto, non più monitorato</div>
</div>
"""


def build_compat_html():
    if not COMPAT_FILE.exists():
        return ""

    with open(COMPAT_FILE, "r", encoding="utf-8") as f:
        compat = json.load(f)

    tutti_ok = compat.get("tutti_compatibili", False)
    badge = (
        '<span class="badge badge-ok">Tutto compatibile</span>'
        if tutti_ok
        else '<span class="badge badge-ko">Problemi rilevati</span>'
    )

    righe = []
    for c in compat.get("controlli", []):
        classe = "compat-ok" if c["ok"] else "compat-ko"
        simbolo = "✅" if c["ok"] else "❌"
        righe.append(
            f'<div class="compat-riga {classe}">{simbolo} <b>{c["check"]}</b>: {c["dettaglio"]}</div>'
        )

    return f"""
<div class="card">
  <h2>🔧 Compatibilità build {badge}</h2>
  {"".join(righe)}
  <div class="compat-nota">{compat.get("nota", "")}</div>
</div>
"""


def load_acquistati():
    if not ACQUISTATI_FILE.exists():
        return []
    with open(ACQUISTATI_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("acquistati", [])


def build_acquistati_html(acquistati):
    if not acquistati:
        return ""
    cards = "".join(
        ACQUISTATO_CARD_TEMPLATE.format(nome=a["nome"], prezzo=a["prezzo"])
        for a in acquistati
    )
    return f'<div class="section-label">Componenti già acquistati</div>{cards}'


def build_total_html(history, acquistati):
    totale = 0.0
    n_componenti = 0
    n_mancanti = 0

    for comp_data in history.values():
        prezzi = comp_data.get("prezzi", [])
        if prezzi:
            totale += prezzi[-1]["prezzo"]
            n_componenti += 1
        else:
            n_mancanti += 1

    totale_acquistati = sum(a["prezzo"] for a in acquistati)
    totale += totale_acquistati
    n_componenti += len(acquistati)

    if n_componenti == 0:
        return ""

    nota_mancanti = (
        f" · {n_mancanti} componenti senza prezzo ancora" if n_mancanti else ""
    )
    nota_acquistati = (
        f" · {len(acquistati)} già acquistati ({totale_acquistati:.2f} €)"
        if acquistati
        else ""
    )

    return f"""
<div class="total-card">
  <div class="total-label">Totale build ({n_componenti} componenti)</div>
  <div class="total-value">{totale:.2f} €</div>
  <div class="total-meta">Prezzi più bassi trovati + componenti già acquistati{nota_mancanti}{nota_acquistati}</div>
</div>
"""


def build():
    history = {}
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    acquistati = load_acquistati()

    cards_html = []
    chart_data = {}

    for comp_id, comp_data in history.items():
        nome = comp_data.get("nome", comp_id)
        prezzi = comp_data.get("prezzi", [])

        if prezzi:
            last = prezzi[-1]
            link_html = (
                f'<a class="price-link" href="{last["url"]}" target="_blank" rel="noopener">Apri offerta ↗</a>'
                if last.get("url")
                else ""
            )
            price_html = (
                f'<div class="price-now">{last["prezzo"]:.2f} €</div>'
                f'<div class="price-meta">fonte: {last.get("fonte","?")} · '
                f'{last["data"][:16].replace("T"," ")}</div>'
                f'{link_html}'
            )
            labels = [p["data"][:10] for p in prezzi]
            prices = [p["prezzo"] for p in prezzi]
            urls = [p.get("url") for p in prezzi]
        else:
            price_html = '<div class="no-data">Nessun dato ancora</div>'
            labels, prices, urls = [], [], []

        chart_data[comp_id] = {"labels": labels, "prices": prices, "urls": urls}
        cards_html.append(
            CARD_TEMPLATE.format(nome=nome, price_html=price_html, id=comp_id)
        )

    html = TEMPLATE.format(
        last_update=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        total_html=build_total_html(history, acquistati),
        compat_html=build_compat_html(),
        acquistati_html=build_acquistati_html(acquistati),
        cards="\n".join(cards_html) if cards_html else '<p class="no-data">Nessun componente monitorato ancora.</p>',
        chart_data_json=json.dumps(chart_data, ensure_ascii=False),
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generata: {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
