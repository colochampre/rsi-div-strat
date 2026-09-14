"""Contrasta las señales generadas contra los exports de TradingView.

Sin esto, senales.py es una hipótesis. Los 70 exports son el conjunto de
prueba: si la reimplementación dispara en las mismas velas en que TradingView
abrió posición, reproduce la estrategia; si no, se ve acá y no más tarde,
cuando los números ya estén publicados.

Dos medidas, y las dos importan:

  cubiertas   entradas del export que caen en una vela donde también
              disparamos nosotros. Es lo que no podemos perder.
  sobrantes   señales nuestras sin entrada correspondiente. La mayoría son
              esperables: TradingView ignora una señal si ya hay posición
              abierta en esa dirección. Las que caen con la posición cerrada
              son las que delatan un error de traducción.

Uso:
    python monitor/validar_senales.py            # una muestra de 6 pares
    python monitor/validar_senales.py AAVE SFP   # pares puntuales
    python monitor/validar_senales.py --todos
"""
import datetime
import glob
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BME = os.environ.get("BME_PATH") or os.path.join(os.path.dirname(RAIZ), "bar-magnifier-estimator")
if not os.path.isdir(BME):
    sys.exit("No encuentro bar-magnifier-estimator en %s. Cloná el repo al lado de este,\n"
             "o apuntá BME_PATH a donde esté." % BME)
sys.path.insert(0, BME)
sys.path.insert(0, AQUI)

from bme import candles, tradingview           # noqa: E402
import senales                                  # noqa: E402

EXPORTS = os.path.join(RAIZ, "backtest", "SL 5.0 - Trailing 3.0 Offset 0.6")
TF = "4h"
OFFSET = 3                      # los exports vienen en UTC-3
CALENTAMIENTO = 500             # velas previas a la primera operación, como max_bars_back


def archivos():
    out = {}
    for f in sorted(glob.glob(os.path.join(EXPORTS, "*.csv"))):
        m = re.search(r"v1\.3_([A-Z]+)_([A-Z0-9]+)\.P_", os.path.basename(f))
        if m and m.group(1) == "BINANCE":
            out[m.group(2)] = f
    return out


def validar(sym, path, proveedor):
    trades = tradingview.read_trades(path, OFFSET)
    paso = datetime.timedelta(hours=4)
    desde = min(t.entry_time for t in trades) - paso * CALENTAMIENTO
    hasta = max(t.exit_time for t in trades) + paso * 2
    serie = proveedor.series(sym, TF, desde, hasta)
    velas = serie.candles
    cuando = [datetime.datetime.fromtimestamp(c.time / 1000, datetime.timezone.utc) for c in velas]

    # La orden se ejecuta en la apertura de la vela siguiente a la señal. Las
    # señales previas a la primera operación del export caen en el
    # calentamiento: son reales, pero no hay con qué compararlas.
    primera = min(t.entry_time for t in trades)
    ultima = max(t.exit_time for t in trades)
    disparos = senales.divergencias(velas)
    predichas = {cuando[s.index + 1]: s.long for s in disparos
                 if s.index + 1 < len(velas) and primera <= cuando[s.index + 1] <= ultima}

    exportadas = {t.entry_time: t.long for t in trades}
    cubiertas = sum(1 for e in exportadas if e in predichas)
    direccion = sum(1 for e, l in exportadas.items() if e in predichas and predichas[e] != l)

    # Una señal sobrante se explica sola si la posición seguía abierta. El caso
    # del borde es la vela donde la posición cerró: el cierre pasa adentro de
    # la vela, así que al cierre de esa misma vela TradingView todavía la tenía
    # abierta cuando evaluó la señal.
    abiertas = [(t.entry_time, t.exit_time) for t in trades]
    sobrantes = [p for p in predichas if p not in exportadas]
    dentro = sum(1 for p in sobrantes if any(a <= p < b for a, b in abiertas))
    cierre = sum(1 for p in sobrantes
                 if not any(a <= p < b for a, b in abiertas)
                 and any(b <= p < b + paso for _a, b in abiertas))
    return dict(sym=sym, n=len(exportadas), cubiertas=cubiertas, direccion=direccion,
                sobrantes=len(sobrantes), dentro=dentro, cierre=cierre,
                fuera=len(sobrantes) - dentro - cierre, velas=len(velas))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    todos = "--todos" in sys.argv
    disponibles = archivos()
    if args:
        elegidos = [a if a.endswith("USDT") else a + "USDT" for a in args]
    elif todos:
        elegidos = sorted(disponibles)
    else:
        elegidos = ["AAVEUSDT", "SFPUSDT", "BATUSDT", "NEOUSDT", "STXUSDT", "DOGSUSDT"]
    proveedor = candles.get_provider("binance")

    print("%-14s %6s %9s %8s %10s %9s %8s %9s" % (
        "par", "export", "cubiertas", "%", "sobrantes", "en pos.", "cerro", "sin expl."))
    tot = dict(n=0, cubiertas=0, sobrantes=0, dentro=0, cierre=0, fuera=0, direccion=0)
    for sym in elegidos:
        if sym not in disponibles:
            print("%-14s sin export" % sym)
            continue
        r = validar(sym, disponibles[sym], proveedor)
        for k in tot:
            tot[k] += r[k]
        print("%-14s %6d %9d %7.1f%% %10d %9d %8d %9d%s" % (
            r["sym"], r["n"], r["cubiertas"], 100.0 * r["cubiertas"] / r["n"],
            r["sobrantes"], r["dentro"], r["cierre"], r["fuera"],
            "  DIRECCION x%d" % r["direccion"] if r["direccion"] else ""))
    if tot["n"]:
        print("%-14s %6d %9d %7.1f%% %10d %9d %8d %9d" % (
            "TOTAL", tot["n"], tot["cubiertas"], 100.0 * tot["cubiertas"] / tot["n"],
            tot["sobrantes"], tot["dentro"], tot["cierre"], tot["fuera"]))
        if tot["direccion"]:
            print("señales con la dirección invertida: %d" % tot["direccion"])


if __name__ == "__main__":
    main()
