"""
Controlla la compatibilita' tra i componenti definiti in build.json.

Regole verificate:
- Socket CPU == Socket scheda madre
- Tipo RAM CPU/scheda madre == tipo RAM acquistata
- Dissipatore supporta il socket della CPU
- Alimentatore ha abbastanza margine di potenza (CPU + GPU + margine sistema)
- SSD M.2 compatibile con la scheda madre

NOTA: questo NON e' un controllo esaustivo di tutte le compatibilita'
fisiche possibili (es. ingombro fisico nel case, lunghezza GPU, altezza
dissipatore per case specifici). Verifica sempre anche le dimensioni
fisiche rispetto al tuo case.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_FILE = ROOT / "build.json"
OUTPUT_FILE = ROOT / "data" / "compatibility.json"

MARGINE_PSU_CONSIGLIATO = 0.20


def check():
    with open(BUILD_FILE, "r", encoding="utf-8") as f:
        build = json.load(f)

    risultati = []

    cpu = build.get("cpu", {})
    mobo = build.get("scheda_madre", {})
    gpu = build.get("gpu", {})
    dissipatore = build.get("dissipatore", {})
    ram = build.get("ram", {})
    psu = build.get("alimentatore", {})
    ssd = build.get("ssd", {})

    if cpu.get("socket") and mobo.get("socket"):
        ok = cpu["socket"] == mobo["socket"]
        risultati.append({
            "check": "Socket CPU / scheda madre",
            "ok": ok,
            "dettaglio": f"{cpu['nome']} ({cpu['socket']}) su {mobo['nome']} ({mobo['socket']})",
        })

    if mobo.get("tipo_ram") and ram.get("tipo"):
        ok = mobo["tipo_ram"] == ram["tipo"]
        risultati.append({
            "check": "Tipo RAM",
            "ok": ok,
            "dettaglio": f"Scheda madre richiede {mobo['tipo_ram']}, RAM scelta e' {ram['tipo']}",
        })

    if dissipatore.get("socket_supportati") and cpu.get("socket"):
        ok = cpu["socket"] in dissipatore["socket_supportati"]
        risultati.append({
            "check": "Dissipatore / socket CPU",
            "ok": ok,
            "dettaglio": f"{dissipatore['nome']} supporta {', '.join(dissipatore['socket_supportati'])}",
        })

    if psu.get("watt") and cpu.get("tdp_watt") and gpu.get("tdp_watt"):
        consumo_stimato = cpu["tdp_watt"] + gpu["tdp_watt"] + 100
        margine_reale = (psu["watt"] - consumo_stimato) / psu["watt"]
        ok = margine_reale >= MARGINE_PSU_CONSIGLIATO
        risultati.append({
            "check": "Potenza alimentatore",
            "ok": ok,
            "dettaglio": (
                f"Consumo stimato ~{consumo_stimato}W (CPU {cpu['tdp_watt']}W + "
                f"GPU {gpu['tdp_watt']}W + ~100W resto sistema) su alimentatore "
                f"da {psu['watt']}W → margine {margine_reale:.0%} "
                f"({'sufficiente' if ok else 'stretto, consigliato PSU piu potente'})"
            ),
        })

    if ssd.get("interfaccia") and "PCIe5" in ssd.get("interfaccia", "") and not mobo.get("supporta_pcie5_m2"):
        risultati.append({
            "check": "SSD M.2 PCIe5",
            "ok": False,
            "dettaglio": f"{ssd['nome']} e' PCIe5 ma la scheda madre non risulta supportarlo esplicitamente (funzionera' comunque in PCIe4)",
        })
    elif ssd.get("nome"):
        risultati.append({
            "check": "SSD M.2",
            "ok": True,
            "dettaglio": f"{ssd['nome']} compatibile con slot M.2 NVMe standard",
        })

    tutti_ok = all(r["ok"] for r in risultati)

    output = {
        "tutti_compatibili": tutti_ok,
        "controlli": risultati,
        "nota": (
            "Controllo automatico su compatibilita' elettrica/socket/RAM. "
            "Verifica sempre manualmente ingombro fisico (lunghezza GPU, "
            "altezza dissipatore, spazio radiatore) rispetto al tuo case."
        ),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Compatibilita' complessiva: {'OK' if tutti_ok else 'PROBLEMI RILEVATI'}")
    for r in risultati:
        stato = "✅" if r["ok"] else "❌"
        print(f"{stato} {r['check']}: {r['dettaglio']}")

    return output


if __name__ == "__main__":
    check()
