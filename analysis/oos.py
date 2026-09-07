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
                        fav=f(r["Favorable excursion %"]), adv=f(r["Adverse excursion %"]),
                        date=r["Date and time"])
        else:
            t[n]["entry"] = True
            t[n]["edate"] = r["Date and time"]
    return [v for v in t.values() if "sig" in v and v.get("entry") and v["ret"] is not None]

files = sorted(glob.glob(BASE + "*_1.0-0.5_*.csv")) + sorted(glob.glob(BASE + "*_1.0-1.0_*.csv"))
D = {}
for p in files:
    name = os.path.basename(p)
    sym = name.split("USDT")[0]
    off = "0.5" if "1.0-0.5" in name else "1.0"
    D[f"{sym} {off}"] = load(p)

def cfg(ts):
    slx = [t for t in ts if t["sig"] == "Stop Loss"]
    tpx = [t for t in ts if t["sig"] == "Take Profit"]
    trx = [t for t in ts if t["sig"] == "Trailing Stop"]
    return (abs(statistics.median(t["ret"] for t in slx)) - 0.1 if slx else None,
            statistics.median(t["ret"] for t in tpx) + 0.1 if tpx else None,
            statistics.median(t["fav"] - t["ret"] for t in trx) - 0.05 if trx else None)

print("=" * 92)
print("0. CONSISTENCIA DE CONFIG  (inferida de los datos, no del nombre)")
print("=" * 92)
print(f"{'Corrida':<14}{'SL':>8}{'TP':>8}{'offset':>9}{'trades':>8}{'desde':>13}{'hasta':>13}")
print("-" * 92)
for k, ts in D.items():
    sl, tp, off = cfg(ts)
    ds = sorted(t["edate"] for t in ts)
    print(f"{k:<14}{sl:>7.2f}%{tp:>7.2f}%{off:>8.2f}%{len(ts):>8}{ds[0][:10]:>13}{ds[-1][:10]:>13}")

print("\n" + "=" * 92)
print("1. RESULTADO POR SIMBOLO")
print("=" * 92)
print(f"{'Corrida':<14}{'Trades':>8}{'Ret neto':>11}{'Winrate':>9}{'PF':>7}{'AvgTrade':>10}{'MaxDD':>9}")
print("-" * 92)
res = {}
for k, ts in D.items():
    wins = [t for t in ts if t["ret"] > 0]
    gw = sum(t["ret"] for t in wins); gl = -sum(t["ret"] for t in ts if t["ret"] <= 0)
    eq = peak = dd = 0.0
    for t in ts:
        eq += t["ret"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    pf = gw / gl if gl else float("inf")
    res[k] = (sum(t["ret"] for t in ts), pf, dd)
    print(f"{k:<14}{len(ts):>8}{sum(t['ret'] for t in ts):>10.1f}pp{100*len(wins)/len(ts):>8.1f}%"
          f"{pf:>7.2f}{statistics.mean(t['ret'] for t in ts):>9.2f}%{dd:>8.1f}pp")

print("\n" + "=" * 92)
print("2. PISO — peor salida por trailing  (teorico neto = act - off - 0.1)")
print("=" * 92)
print(f"{'Corrida':<14}{'teorico':>10}{'peor real':>12}{'perdedoras':>14}{'coincide':>11}")
print("-" * 92)
for k, ts in D.items():
    tr = [t for t in ts if t["sig"] == "Trailing Stop"]
    off = 0.5 if k.endswith("0.5") else 1.0
    teo = ACT - off - 0.1
    peor = min(t["ret"] for t in tr)
    los = sum(1 for t in tr if t["ret"] < 0)
    print(f"{k:<14}{teo:>+9.1f}%{peor:>+11.2f}%{los:>9}/{len(tr):<4}{('si' if abs(peor-teo)<0.15 else 'NO'):>11}")

print("\n" + "=" * 92)
print("3. AMBIGUEDAD — intra-vela donde el orden decidiria el signo")
print("=" * 92)
print(f"{'Corrida':<14}{'trail':>7}{'intra':>8}{'%intra':>8}{'ambiguos':>10}{'peor adv':>11}{'SL':>8}{'margen':>9}")
print("-" * 92)
for k, ts in D.items():
    sl, _, _ = cfg(ts)
    tr = [t for t in ts if t["sig"] == "Trailing Stop"]
    intra = [t for t in tr if t["dur"] == 0]
    amb = [t for t in intra if abs(t["adv"]) >= sl]
    padv = max(abs(t["adv"]) for t in intra) if intra else 0.0
    print(f"{k:<14}{len(tr):>7}{len(intra):>8}{100*len(intra)/len(tr):>7.0f}%{len(amb):>10}"
          f"{padv:>10.2f}%{sl:>7.2f}%{sl-padv:>8.2f}pp")

print("\n" + "=" * 92)
print("4. SLIPPAGE — sobrevive el resultado a 0.05% por salida por trailing?")
print("=" * 92)
print(f"{'Corrida':<14}{'ret bruto':>12}{'coste slip':>12}{'ret ajustado':>14}{'PF ajust.':>11}{'veredicto':>12}")
print("-" * 92)
for k, ts in D.items():
    tr = [t for t in ts if t["sig"] == "Trailing Stop"]
    coste = 0.05 * len(tr)
    tot = sum(t["ret"] for t in ts)
    adj = [t["ret"] - (0.05 if t["sig"] == "Trailing Stop" else 0) for t in ts]
    gw = sum(r for r in adj if r > 0); gl = -sum(r for r in adj if r <= 0)
    pf = gw / gl if gl else float("inf")
    print(f"{k:<14}{tot:>11.1f}pp{-coste:>11.1f}pp{tot-coste:>13.1f}pp{pf:>11.2f}"
          f"{('POSITIVO' if tot-coste > 0 else 'NEGATIVO'):>12}")

print("\n" + "=" * 92)
print("5. DESGLOSE POR TIPO DE SALIDA")
print("=" * 92)
print(f"{'Corrida':<14}{'Trailing':>22}{'Take Profit':>22}{'Stop Loss':>22}")
print(f"{'':<14}{'N   sum    avg':>22}{'N   sum    avg':>22}{'N   sum    avg':>22}")
print("-" * 92)
for k, ts in D.items():
    by = collections.defaultdict(list)
    for t in ts:
        by[t["sig"]].append(t)
    cells = ""
    for sig in ("Trailing Stop", "Take Profit", "Stop Loss"):
        g = by.get(sig, [])
        if g:
            cells += f"{len(g):>5}{sum(t['ret'] for t in g):>8.0f}pp{statistics.mean(t['ret'] for t in g):>7.2f}%"
        else:
            cells += f"{'-':>22}"
    print(f"{k:<14}{cells}")

print("\n" + "=" * 92)
print("6. VEREDICTO OUT-OF-SAMPLE")
print("=" * 92)
oos = {k: v for k, v in res.items() if k.endswith("0.5") and not k.startswith("SOL")}
insample = {k: v for k, v in res.items() if k.startswith("SOL")}
print(f"In-sample (SOL, donde se ajustaron los parametros):")
for k, (r, pf, dd) in insample.items():
    print(f"  {k:<12} {r:>8.1f}pp   PF {pf:.2f}   DD {dd:.1f}pp")
print(f"\nOut-of-sample (config congelada, simbolos no usados para ajustar):")
for k, (r, pf, dd) in sorted(oos.items(), key=lambda x: -x[1][0]):
    print(f"  {k:<12} {r:>8.1f}pp   PF {pf:.2f}   DD {dd:.1f}pp")
pfs = [pf for _, pf, _ in oos.values()]
rets = [r for r, _, _ in oos.values()]
print(f"\n  simbolos OOS rentables : {sum(1 for r in rets if r > 0)}/{len(rets)}")
print(f"  simbolos OOS con PF>1  : {sum(1 for p in pfs if p > 1)}/{len(pfs)}")
print(f"  PF OOS mediano         : {statistics.median(pfs):.2f}   (SOL 0.5: {insample.get('SOL 0.5',(0,0,0))[1]:.2f})")
print(f"  retorno OOS mediano    : {statistics.median(rets):.1f}pp")
