"""
Genera docs/index.html a partire da data/prices_history.json.
La cartella docs/ viene pubblicata da GitHub Pages.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "data" / "prices_history.json"
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
  .price-meta {{ font-size: 0.8rem; color: #888; margin-bottom: 12px; }}
  .no-data {{ color: #888; font-style: italic; }}
  canvas {{ max-height: 220px; }}
</style>
</head>
<body>
  <h1>💻 Monitor Prezzi Componenti PC</h1>
  <div class="subtitle">Ultimo aggiornamento: {last_update}</div>
  {cards}
  <script>
    const chartData = {chart_data_json};
    Object.entries(chartData).forEach(([id, d]) => {{
      const ctx = document.getElementById('chart_' + id);
      if (!ctx) return;
      new Chart(ctx, {{
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
          }}]
        }},
        options: {{
          responsive: true,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ ticks: {{ color: '#888' }}, grid: {{ color: '#2a2d35' }} }},
            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: '#2a2d35' }} }}
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
</div>
"""


def build():
    history = {}
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    cards_html = []
    chart_data = {}

    for comp_id, comp_data in history.items():
        nome = comp_data.get("nome", comp_id)
        prezzi = comp_data.get("prezzi", [])

        if prezzi:
            last = prezzi[-1]
            price_html = (
                f'<div class="price-now">{last["prezzo"]:.2f} €</div>'
                f'<div class="price-meta">fonte: {last.get("fonte","?")} · '
                f'{last["data"][:16].replace("T"," ")}</div>'
            )
            labels = [p["data"][:10] for p in prezzi]
            prices = [p["prezzo"] for p in prezzi]
        else:
            price_html = '<div class="no-data">Nessun dato ancora</div>'
            labels, prices = [], []

        chart_data[comp_id] = {"labels": labels, "prices": prices}
        cards_html.append(
            CARD_TEMPLATE.format(nome=nome, price_html=price_html, id=comp_id)
        )

    html = TEMPLATE.format(
        last_update=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        cards="\n".join(cards_html) if cards_html else '<p class="no-data">Nessun componente monitorato ancora.</p>',
        chart_data_json=json.dumps(chart_data, ensure_ascii=False),
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generata: {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
