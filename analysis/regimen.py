import csv, glob, os, collections, statistics

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest") + os.sep

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

D = {}
for p in sorted(glob.glob(BASE + "*_1.0-0.5_*.csv")):
    D[os.path.basename(p).split("USDT")[0]] = load(p)

def pf(ts):
    gw = sum(t["ret"] for t in ts if t["ret"] > 0)
    gl = -sum(t["ret"] for t in ts if t["ret"] <= 0)
    return gw / gl if gl else float("inf")

print("=" * 88)
print("A. VOLATILIDAD vs RENDIMIENTO   (hipotesis: el edge escala con la volatilidad)")
print("=" * 88)
print(f"{'Simbolo':<9}{'recorrido med.':>16}{'PF':>7}{'Ret':>10}{'%intra':>9}{'avg SL':>9}{'avg trail':>11}")
print("-" * 88)
vol = {}
for k, ts in D.items():
    spans = [t["fav"] + abs(t["adv"]) for t in ts]
    v = statistics.median(spans)
    vol[k] = v
    tr = [t for t in ts if t["sig"] == "Trailing Stop"]
    slx = [t for t in ts if t["sig"] == "Stop Loss"]
    intra = sum(1 for t in ts if t["dur"] == 0)
    print(f"{k:<9}{v:>15.2f}%{pf(ts):>7.2f}{sum(t['ret'] for t in ts):>9.0f}pp"
          f"{100*intra/len(ts):>8.0f}%{statistics.mean(t['ret'] for t in slx):>8.2f}%"
          f"{statistics.mean(t['ret'] for t in tr):>10.2f}%")
order_v = sorted(vol, key=vol.get)
order_p = sorted(D, key=lambda k: pf(D[k]))
print(f"\n  orden por volatilidad : {' < '.join(order_v)}")
print(f"  orden por PF          : {' < '.join(order_p)}")
print(f"  coinciden             : {'SI — el edge escala con la volatilidad' if order_v == order_p else 'no exactamente'}")

print("\n" + "=" * 88)
print("B. ESTABILIDAD POR AÑO   (el edge, esta repartido o concentrado en un regimen?)")
print("=" * 88)
years = sorted({t["year"] for ts in D.values() for t in ts})
print(f"{'Simbolo':<9}" + "".join(f"{y:>14}" for y in years))
print(f"{'':<9}" + "".join(f"{'ret / PF':>14}" for y in years))
print("-" * 88)
for k, ts in D.items():
    row = ""
    for y in years:
        g = [t for t in ts if t["year"] == y]
        row += f"{sum(t['ret'] for t in g):>7.0f}pp{pf(g):>6.2f}" if g else f"{'-':>14}"
    print(f"{k:<9}{row}")
print("-" * 88)
row = ""
tot_by_year = {}
for y in years:
    g = [t for ts in D.values() for t in ts if t["year"] == y]
    tot_by_year[y] = (sum(t["ret"] for t in g), pf(g), len(g))
    row += f"{tot_by_year[y][0]:>7.0f}pp{tot_by_year[y][1]:>6.2f}"
print(f"{'POOL':<9}{row}")
print(f"{'trades':<9}" + "".join(f"{tot_by_year[y][2]:>14}" for y in years))

print("\n  Años con PF<1 por simbolo:")
for k, ts in D.items():
    bad = [y for y in years if [t for t in ts if t["year"] == y] and pf([t for t in ts if t["year"] == y]) < 1]
    print(f"    {k:<9} {', '.join(bad) if bad else 'ninguno'}")

print("\n" + "=" * 88)
print("C. CORRELACION ENTRE SIMBOLOS   (cuantos tests INDEPENDIENTES hay realmente?)")
print("=" * 88)
print("Retorno mensual por simbolo -> correlacion de Pearson entre pares\n")
monthly = {}
for k, ts in D.items():
    m = collections.defaultdict(float)
    for t in ts:
        m[t["year"]] = m[t["year"]]
    m = collections.defaultdict(float)
    for t in ts:
        m[t.get("year", "?")] += t["ret"]
    monthly[k] = m

# correlacion sobre retornos ANUALES (pocos puntos, pero indicativo)
def corr(a, b):
    ks = sorted(set(a) & set(b))
    if len(ks) < 3:
        return None
    x = [a[k] for k in ks]; y = [b[k] for k in ks]
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((i-mx)*(j-my) for i, j in zip(x, y))
    den = (sum((i-mx)**2 for i in x) * sum((j-my)**2 for j in y)) ** 0.5
    return num/den if den else None

syms = sorted(D)
print(f"{'':<9}" + "".join(f"{s:>9}" for s in syms))
for a in syms:
    row = ""
    for b in syms:
        c = corr(monthly[a], monthly[b])
        row += f"{c:>9.2f}" if c is not None else f"{'-':>9}"
    print(f"{a:<9}{row}")
cs = [corr(monthly[a], monthly[b]) for i, a in enumerate(syms) for b in syms[i+1:] if corr(monthly[a], monthly[b]) is not None]
if cs:
    print(f"\n  correlacion media entre pares: {statistics.mean(cs):.2f}")
    print(f"  (alta => los 4 simbolos NO son 4 tests independientes)")
