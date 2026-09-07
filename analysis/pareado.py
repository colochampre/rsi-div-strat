import csv, glob, os, collections, statistics

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest") + os.sep
ACT = 1.0
SLIP = 0.05

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
            t[n]["year"] = r["Date and time"][:4]
    return [v for v in t.values() if "sig" in v and v.get("entry") and v["ret"] is not None]

P = collections.defaultdict(dict)
for p in sorted(glob.glob(BASE + "*USDT*_4h_*.csv")):
    b = os.path.basename(p)
    sym = b.split("USDT")[0]
    tag = "0.5" if "1.0-0.5" in b else "1.0"
    P[sym][tag] = load(p)
SYMS = sorted(P)

def pf(ts, slip=0.0):
    r = [t["ret"] - (slip if t["sig"] == "Trailing Stop" else 0) for t in ts]
    gw = sum(x for x in r if x > 0); gl = -sum(x for x in r if x <= 0)
    return gw / gl if gl else float("inf")

def dd(ts):
    eq = peak = m = 0.0
    for t in ts:
        eq += t["ret"]; peak = max(peak, eq); m = max(m, peak - eq)
    return m

def cfg(ts):
    slx = [t for t in ts if t["sig"] == "Stop Loss"]
    tpx = [t for t in ts if t["sig"] == "Take Profit"]
    trx = [t for t in ts if t["sig"] == "Trailing Stop"]
    return (abs(statistics.median(t["ret"] for t in slx)) - 0.1,
            statistics.median(t["ret"] for t in tpx) + 0.1,
            statistics.median(t["fav"] - t["ret"] for t in trx) - 0.05)

print("=" * 94)
print("0. VALIDEZ DEL EXPERIMENTO  (config inferida de los datos + control por Stop Loss)")
print("=" * 94)
print(f"{'Simbolo':<8}{'tag':>5}{'SL':>8}{'TP':>8}{'offset':>9}{'trades':>8}{'SL exits':>10}{'SL sumRet':>12}")
print("-" * 94)
ok_all = True
for s in SYMS:
    for tag in ("1.0", "0.5"):
        ts = P[s][tag]
        sl, tp, off = cfg(ts)
        slx = [t for t in ts if t["sig"] == "Stop Loss"]
        print(f"{s:<8}{tag:>5}{sl:>7.2f}%{tp:>7.2f}%{off:>8.2f}%{len(ts):>8}{len(slx):>10}{sum(t['ret'] for t in slx):>11.1f}pp")
    a, b = P[s]["1.0"], P[s]["0.5"]
    sa = [t for t in a if t["sig"] == "Stop Loss"]; sb = [t for t in b if t["sig"] == "Stop Loss"]
    same = len(sa) == len(sb) and abs(sum(t["ret"] for t in sa) - sum(t["ret"] for t in sb)) < 0.5
    ok_all &= same
    print(f"{'':<8}{'-> control SL identico: ' + ('SI' if same else 'NO'):>60}\n")
print(f"Control global: {'OK — solo cambia el offset' if ok_all else 'ATENCION: cambio algo mas que el offset'}")

print("\n" + "=" * 94)
print("1. COMPARACION PAREADA — offset 1.0% vs 0.5%  (misma activacion, mismo SL/TP)")
print("=" * 94)
print(f"{'Simbolo':<8}{'ret 1.0':>10}{'ret 0.5':>10}{'delta':>10}{'PF 1.0':>9}{'PF 0.5':>9}{'DD 1.0':>9}{'DD 0.5':>9}{'gana':>7}")
print("-" * 94)
wins = 0
for s in SYMS:
    a, b = P[s]["1.0"], P[s]["0.5"]
    ra, rb = sum(t["ret"] for t in a), sum(t["ret"] for t in b)
    w = "0.5" if rb > ra else "1.0"
    wins += rb > ra
    print(f"{s:<8}{ra:>9.1f}pp{rb:>9.1f}pp{rb-ra:>+9.1f}pp{pf(a):>9.2f}{pf(b):>9.2f}"
          f"{dd(a):>8.1f}pp{dd(b):>8.1f}pp{w:>7}")
print("-" * 94)
print(f"offset 0.5% gana en {wins}/{len(SYMS)} simbolos")

print("\n" + "=" * 94)
print(f"2. MISMA COMPARACION CON SLIPPAGE DE {SLIP}% POR SALIDA DE TRAILING")
print("=" * 94)
print(f"{'Simbolo':<8}{'ret 1.0':>10}{'ret 0.5':>10}{'delta':>10}{'PF 1.0':>9}{'PF 0.5':>9}{'gana':>7}")
print("-" * 94)
wins_s = 0
for s in SYMS:
    a, b = P[s]["1.0"], P[s]["0.5"]
    ra = sum(t["ret"] for t in a) - SLIP * sum(1 for t in a if t["sig"] == "Trailing Stop")
    rb = sum(t["ret"] for t in b) - SLIP * sum(1 for t in b if t["sig"] == "Trailing Stop")
    wins_s += rb > ra
    print(f"{s:<8}{ra:>9.1f}pp{rb:>9.1f}pp{rb-ra:>+9.1f}pp{pf(a,SLIP):>9.2f}{pf(b,SLIP):>9.2f}"
          f"{('0.5' if rb>ra else '1.0'):>7}")
print("-" * 94)
print(f"offset 0.5% gana en {wins_s}/{len(SYMS)} simbolos con slippage")

print("\n" + "=" * 94)
print("3. PAREADO POR AÑO — en cuantos simbolo-año gana 0.5?")
print("=" * 94)
years = sorted({t["year"] for s in SYMS for tag in P[s] for t in P[s][tag]})
print(f"{'Simbolo':<8}" + "".join(f"{y:>12}" for y in years) + f"{'gana 0.5':>11}")
print("-" * 94)
tot_w = tot_n = 0
for s in SYMS:
    row = ""; w = n = 0
    for y in years:
        ga = [t for t in P[s]["1.0"] if t["year"] == y]
        gb = [t for t in P[s]["0.5"] if t["year"] == y]
        if not ga or not gb:
            row += f"{'-':>12}"; continue
        d = sum(t["ret"] for t in gb) - sum(t["ret"] for t in ga)
        row += f"{d:>+11.0f}pp"; n += 1; w += d > 0
    tot_w += w; tot_n += n
    print(f"{s:<8}{row}{f'{w}/{n}':>11}")
print("-" * 94)
print(f"{'TOTAL':<8}{'':<{12*len(years)}}{f'{tot_w}/{tot_n}':>11}")

print("\n" + "=" * 94)
print("4. POR QUE GANA — descomposicion del delta")
print("=" * 94)
print(f"{'Simbolo':<8}{'trail N':>16}{'avg trail':>18}{'TP N':>14}{'ret trail':>18}")
print(f"{'':<8}{'1.0 -> 0.5':>16}{'1.0 -> 0.5':>18}{'1.0 -> 0.5':>14}{'delta':>18}")
print("-" * 94)
for s in SYMS:
    a, b = P[s]["1.0"], P[s]["0.5"]
    ta = [t for t in a if t["sig"] == "Trailing Stop"]; tb = [t for t in b if t["sig"] == "Trailing Stop"]
    pa = [t for t in a if t["sig"] == "Take Profit"];   pb = [t for t in b if t["sig"] == "Take Profit"]
    avg_a = statistics.mean(t["ret"] for t in ta)
    avg_b = statistics.mean(t["ret"] for t in tb)
    print(f"{s:<8}{f'{len(ta)} -> {len(tb)}':>16}"
          f"{f'{avg_a:.2f}% -> {avg_b:.2f}%':>18}"
          f"{f'{len(pa)} -> {len(pb)}':>14}"
          f"{sum(t['ret'] for t in tb) - sum(t['ret'] for t in ta):>+17.1f}pp")

print("\n" + "=" * 94)
print("5. PISO Y AMBIGUEDAD POR CONFIG")
print("=" * 94)
print(f"{'Simbolo':<8}{'tag':>5}{'piso teo':>10}{'peor real':>11}{'perdedoras':>13}{'%intra':>9}{'ambiguos':>10}")
print("-" * 94)
for s in SYMS:
    for tag in ("1.0", "0.5"):
        ts = P[s][tag]
        sl, _, _ = cfg(ts)
        tr = [t for t in ts if t["sig"] == "Trailing Stop"]
        intra = [t for t in tr if t["dur"] == 0]
        amb = sum(1 for t in intra if abs(t["adv"]) >= sl)
        teo = ACT - float(tag) - 0.1
        print(f"{s:<8}{tag:>5}{teo:>+9.1f}%{min(t['ret'] for t in tr):>+10.2f}%"
              f"{sum(1 for t in tr if t['ret']<0):>8}/{len(tr):<4}{100*len(intra)/len(tr):>8.0f}%{amb:>10}")
