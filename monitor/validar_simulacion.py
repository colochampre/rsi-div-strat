"""Compara la simulación propia contra el mismo export, punta a punta.

validar_senales.py demuestra que disparamos en las mismas velas. Eso todavía no
alcanza: lo que se publica no son señales sino estadísticas, y una diferencia
chica en qué operaciones se toman puede mover el t lo suficiente como para que
un par cruce el umbral de decisión.

Acá se corre el circuito completo sobre la misma ventana y las mismas velas,
cambiando solo el origen de las entradas:

  export      las entradas que TradingView efectivamente tomó
  simulada    las que genera senales.py con estado de posición

Se compara a 4 horas por defecto, que es la resolución con la que TradingView
produjo esos exports. Comparar a 5 minutos mezcla dos preguntas distintas: si
la reimplementación es fiel, y cuánto cambia el resultado al mirar más fino.
Esa segunda ya la respondió la auditoría.

También se corre sin la reentrada intravela, para que se vea cuánto aporta
modelar el recálculo de calc_on_order_fills en vez de ignorarlo.

Uso:
    python monitor/validar_simulacion.py               # muestra de 6 pares, a 4h
    python monitor/validar_simulacion.py --tf 5m
    python monitor/validar_simulacion.py AAVE SFP
"""
import datetime
import math
import os
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BME = os.environ.get("BME_PATH") or os.path.join(os.path.dirname(RAIZ), "bar-magnifier-estimator")
if not os.path.isdir(BME):
    sys.exit("No encuentro bar-magnifier-estimator en %s." % BME)
sys.path.insert(0, BME)
sys.path.insert(0, AQUI)

from bme import candles, estimate, tradingview   # noqa: E402
import simular                                   # noqa: E402
import validar_senales as vs                     # noqa: E402

MUESTRA = ["AAVEUSDT", "SFPUSDT", "BATUSDT", "NEOUSDT", "STXUSDT", "DOGSUSDT"]
PASO = datetime.timedelta(hours=4)


def stats(rets):
    if len(rets) < 2:
        return dict(n=len(rets), total=sum(rets), t=0.0)
    sd = statistics.pstdev(rets)
    return dict(n=len(rets), total=sum(rets),
                t=statistics.mean(rets) / (sd / math.sqrt(len(rets))) if sd else 0.0)


def comparar(sym, path, proveedor, tf):
    trades = tradingview.read_trades(path, vs.OFFSET)
    primera = min(t.entry_time for t in trades)
    ultima = max(t.exit_time for t in trades)

    exp = estimate.run(trades, proveedor, sym, tf, simular.reglas(), simular.COMISION)
    ref = {t.entry_time: f.pct for t, f in exp.pairs if f is not None}

    velas = proveedor.series(sym, simular.CHART_TF,
                             primera - PASO * simular.CALENTAMIENTO, ultima + PASO * 2).candles
    fina = proveedor.series(sym, tf, primera - PASO,
                            ultima + datetime.timedelta(hours=simular.MAX_HORAS))
    out = [("export", stats(list(ref.values())), 0, 0)]
    for etiqueta, flag in (("con reent.", True), ("sin reent.", False)):
        ops = [o for o in simular.operaciones(velas, fina, reentrada_intravela=flag, fine_tf=tf)
               if primera <= o.entrada <= ultima]
        mias = {}
        for o in ops:
            mias.setdefault(o.entrada, o.ret)
        out.append((etiqueta, stats([o.ret for o in ops]),
                    len(set(mias) - set(ref)), len(set(ref) - set(mias))))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tf = "4h"
    if "--tf" in sys.argv:
        i = sys.argv.index("--tf")
        tf = sys.argv[i + 1]
        args = [a for a in args if a != tf]
    disponibles = vs.archivos()
    elegidos = ([a if a.endswith("USDT") else a + "USDT" for a in args] if args
                else (sorted(disponibles) if "--todos" in sys.argv else MUESTRA))
    proveedor = candles.get_provider("binance")

    print("salidas replayadas a %s\n" % tf)
    print("%-12s %-11s %5s %7s %6s %9s %7s %8s" % (
        "par", "variante", "ops", "total", "t", "dif total", "dif t", "extra/falta"))
    acum = {}
    for sym in elegidos:
        if sym not in disponibles:
            print("%-12s sin export" % sym)
            continue
        filas = comparar(sym, disponibles[sym], proveedor, tf)
        base = filas[0][1]
        for etiqueta, s, extras, faltan in filas:
            if etiqueta == "export":
                print("%-12s %-11s %5d %6.0f%% %6.2f" % (sym, etiqueta, s["n"], s["total"], s["t"]))
                continue
            acum.setdefault(etiqueta, []).append(
                (abs(s["total"] - base["total"]), abs(s["t"] - base["t"]), extras, faltan))
            print("%-12s %-11s %5d %6.0f%% %6.2f %8.0fpp %7.2f %5d/%d" % (
                "", etiqueta, s["n"], s["total"], s["t"],
                s["total"] - base["total"], s["t"] - base["t"], extras, faltan))
    print()
    for etiqueta, filas in acum.items():
        print("%-11s error medio: total %5.1fpp | t %.3f | extras %d | faltan %d" % (
            etiqueta, statistics.mean(f[0] for f in filas), statistics.mean(f[1] for f in filas),
            sum(f[2] for f in filas), sum(f[3] for f in filas)))


if __name__ == "__main__":
    main()
