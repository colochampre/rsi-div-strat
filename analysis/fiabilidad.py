import csv, glob, os, collections, statistics

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest") + os.sep
ACT = 1.0

def f(v):
    try:
        return float(v)
    except Exception:
        return None

def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    t = collections.defaultdict(dict)
    for r in rows:
        n = r["Trade number"]
        if r["Type"].lower().startswith("exit"):
            t[n].update(sig=r["Signal"], dur=f(r["Duration (bars)"]), ret=f(r["Return %"]),
                        fav=f(r["Favorable excursion %"]), adv=f(r["Adverse excursion %"]))
        else:
            t[n]["entry"] = True
    return [v for v in t.values() if "sig" in v and v.get("entry") and v["ret"] is not None]

P = collections.defaultdict(dict)
for p in sorted(glob.glob(BASE + "*USDT*_4h_*.csv")):
    b = os.path.basename(p)
    P[b.split("USDT")[0]]["0.5" if "1.0-0.5" in b else "1.0"] = load(p)
SYMS = sorted(P)

def sl_of(ts):
    slx = [t for t in ts if t["sig"] == "Stop Loss"]
    return abs(statistics.median(t["ret"] for t in slx)) - 0.1

def clasificar(ts, sl):
    """Un trade es ORDEN-DEPENDIENTE si dentro de su recorrido eran alcanzables
    tanto la salida ganadora como el SL. El high y el low son hechos; lo unico
    que el emulador asume es cual se toco primero."""
    det, dep_win, dep_loss = [], [], []
    for t in ts:
        gano = t["ret"] > 0
        sl_alcanzable = abs(t["adv"]) >= sl
        # para un trade perdedor: llego a armar el trailing? entonces habia salida ganadora
        win_alcanzable = t["fav"] >= ACT
        if gano and sl_alcanzable:
            dep_win.append(t)      # el emulador eligio la ganancia
        elif not gano and win_alcanzable:
            dep_loss.append(t)     # el emulador eligio la perdida
        else:
            det.append(t)
    return det, dep_win, dep_loss

print("=" * 96)
print("1. FIABILIDAD — que fraccion del resultado NO depende del orden asumido")
print("=" * 96)
print(f"{'Simbolo':<8}{'off':>5}{'trades':>8}{'determin.':>11}{'%det':>7}{'dep-gana':>10}{'dep-pierde':>12}{'pp en juego':>13}")
print("-" * 96)
R = {}
for s in SYMS:
    for tag in ("1.0", "0.5"):
        ts = P[s][tag]
        sl = sl_of(ts)
        det, dw, dl = clasificar(ts, sl)
        enjuego = sum(t["ret"] for t in dw) - sum(t["ret"] for t in dl)
        R[(s, tag)] = (det, dw, dl)
        print(f"{s:<8}{tag:>5}{len(ts):>8}{len(det):>11}{100*len(det)/len(ts):>6.0f}%"
              f"{len(dw):>10}{len(dl):>12}{enjuego:>12.1f}pp")

print("\n" + "=" * 96)
print("2. COTA PESIMISTA — y si TODO trade orden-dependiente sale como peor caso?")
print("=" * 96)
print("   dep-gana  -> se fuerza a Stop Loss")
print("   dep-pierde-> se deja como esta (ya es el peor caso)")
print("   ademas: 0.05% de slippage en cada salida por trailing\n")
print(f"{'Simbolo':<8}{'off':>5}{'reportado':>12}{'pesimista':>12}{'perdida':>10}{'PF pesim.':>11}{'veredicto':>12}")
print("-" * 96)
for s in SYMS:
    for tag in ("1.0", "0.5"):
        ts = P[s][tag]
        sl = sl_of(ts)
        det, dw, dl = clasificar(ts, sl)
        rep = sum(t["ret"] for t in ts) - 0.05 * sum(1 for t in ts if t["sig"] == "Trailing Stop")
        peor = []
        for t in ts:
            r = t["ret"] - (0.05 if t["sig"] == "Trailing Stop" else 0)
            if t in dw:
                r = -(sl + 0.1)
            peor.append(r)
        gw = sum(x for x in peor if x > 0); gl = -sum(x for x in peor if x <= 0)
        tot = sum(peor)
        print(f"{s:<8}{tag:>5}{rep:>11.1f}pp{tot:>11.1f}pp{tot-rep:>9.1f}pp"
              f"{gw/gl:>11.2f}{('ROBUSTO' if tot > 0 else 'CAE'):>12}")

print("\n" + "=" * 96)
print("3. EL PROBLEMA DE FONDO — tamano de vela vs distancia de los niveles")
print("=" * 96)
print(f"{'Simbolo':<8}{'rango vela*':>14}{'SL':>8}{'act+off':>10}{'ratio SL':>11}{'ratio trail':>13}{'%intra':>9}")
print("-" * 96)
for s in SYMS:
    ts = P[s]["0.5"]
    sl = sl_of(ts)
    spans = [t["fav"] + abs(t["adv"]) for t in ts if t["dur"] == 0]
    rango = statistics.median(spans)
    intra = 100 * sum(1 for t in ts if t["dur"] == 0) / len(ts)
    print(f"{s:<8}{rango:>13.2f}%{sl:>7.2f}%{ACT+0.5:>9.1f}%"
          f"{sl/rango:>11.2f}{(ACT+0.5)/rango:>13.2f}{intra:>8.0f}%")
print("\n* rango mediano de las velas donde el trade se resolvio en una sola vela")
print("  ratio > 1  => el nivel esta FUERA de la vela tipica -> el emulador no puede inventarlo")
print("  ratio < 1  => el nivel CABE dentro de la vela tipica -> el orden asumido decide")

print("\n" + "=" * 96)
print("4. QUE TIMEFRAME HARIA FALTA")
print("=" * 96)
r4 = statistics.median([statistics.median([t["fav"] + abs(t["adv"]) for t in P[s]["0.5"] if t["dur"] == 0]) for s in SYMS])
print(f"Rango mediano de vela en 4h: {r4:.2f}%")
print(f"Para que act+off ({ACT+0.5:.1f}%) supere el rango de vela hace falta rango < {ACT+0.5:.1f}%")
print(f"Para que el SL (~1.9%) lo supere hace falta rango < 1.9%\n")
print(f"{'Timeframe':<12}{'rango estimado**':>18}{'ratio trail':>14}{'ratio SL':>11}{'fiable?':>10}")
print("-" * 96)
for tf, factor in (("4h", 1.0), ("2h", 0.707), ("1h", 0.5), ("30m", 0.354), ("15m", 0.25)):
    r = r4 * factor
    rt, rs = (ACT + 0.5) / r, 1.9 / r
    print(f"{tf:<12}{r:>17.2f}%{rt:>14.2f}{rs:>11.2f}{('SI' if rt > 1 and rs > 1 else 'no'):>10}")
print("\n** escalado por raiz del tiempo (aproximacion estandar de volatilidad)")
