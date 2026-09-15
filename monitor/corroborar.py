"""Mide pares desde exports de TradingView y los deja junto a los simulados.

El simulador de actualizar.py mira los 65 pares todos los meses sin que nadie
mueva un dedo, pero no puede reproducir el 2,8% de operaciones que nacen del
recálculo intravela de TradingView, y eso le deja el t más bajo —hasta 0,84 en
algún par—. Sirve para detectar movimiento, no para decidir.

Un export sí está en la misma escala que el informe. Así que la división de
tareas es: el simulador nomina, el export decide.

Este script toma los CSV que dejes en backtest/corroboracion/ (o la carpeta que
le pases), los mide con las mismas reglas y resolución que el informe, y guarda
el resultado al lado del simulado. La página muestra las dos columnas y aclara
cuál manda.

No hace falta exportar los 65. Con la cartera y los que el monitor haya
nominado alcanza: diez o quince archivos.

Uso:
    python monitor/corroborar.py
    python monitor/corroborar.py ruta/a/otra/carpeta
"""
import datetime
import glob
import io
import json
import math
import os
import re
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BME = os.environ.get("BME_PATH") or os.path.join(os.path.dirname(RAIZ), "bar-magnifier-estimator")
if not os.path.isdir(BME):
    sys.exit("No encuentro bar-magnifier-estimator en %s." % BME)
sys.path.insert(0, BME)
sys.path.insert(0, AQUI)

from bme import candles, estimate, tradingview     # noqa: E402
import actualizar                                  # noqa: E402
import simular                                     # noqa: E402

CARPETA = os.path.join(RAIZ, "backtest", "corroboracion")
OFFSET = 3                      # los exports vienen en UTC-3


def archivos(carpeta):
    out = {}
    for f in sorted(glob.glob(os.path.join(carpeta, "*.csv"))):
        m = re.search(r"_([A-Z]+)_([A-Z0-9]+)\.P_", os.path.basename(f))
        if m and m.group(1) == "BINANCE":
            out[m.group(2)] = f
    return out


def medir(sym, path, proveedor):
    """Las mismas reglas, resolución y costos que usa el informe."""
    trades = tradingview.read_trades(path, OFFSET)
    trades = [t for t in trades if t.entry_time >= actualizar.MEDIR_DESDE]
    if len(trades) < 2:
        return None
    res = estimate.run(trades, proveedor, sym, simular.FINE_TF,
                       simular.reglas(), simular.COMISION)
    llenas = [(t, f) for t, f in res.pairs if f is not None]
    if len(llenas) < 2:
        return None
    fee = estimate.funding_cost([t for t, _f in llenas], proveedor, sym)
    rets = [f.pct - c for (_t, f), c in zip(llenas, fee)]
    sd = statistics.pstdev(rets)
    return dict(n=len(rets), total=round(sum(rets), 1),
                t=round(statistics.mean(rets) / (sd / math.sqrt(len(rets))), 3) if sd else 0.0,
                desde=llenas[0][0].entry_time.strftime("%Y-%m"),
                hasta=llenas[-1][0].exit_time.strftime("%Y-%m"),
                medido=datetime.date.today().isoformat())


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else CARPETA
    if not os.path.isdir(carpeta):
        sys.exit("No existe %s. Dejá ahí los exports de 'List of Trades'." % carpeta)
    encontrados = archivos(carpeta)
    if not encontrados:
        sys.exit("No hay CSV de Binance en %s." % carpeta)

    estado = actualizar.leer(actualizar.ESTADO, None)
    if estado is None:
        sys.exit("Todavía no hay estado.json. Corré antes monitor/actualizar.py.")
    proveedor = candles.get_provider("binance")

    print("corroborando %d pares contra sus exports\n" % len(encontrados))
    print("%-14s %5s %8s %7s %9s %8s" % ("par", "ops", "total", "t", "t simulado", "desvio"))
    for sym in sorted(encontrados):
        try:
            st = medir(sym, encontrados[sym], proveedor)
        except Exception as exc:
            print("%-14s ERROR %s: %s" % (sym, type(exc).__name__, exc))
            continue
        if st is None:
            print("%-14s sin operaciones suficientes" % sym)
            continue
        fila = estado["pares"].setdefault(sym, {})
        fila["corroborado"] = st
        sim = fila.get("t")
        print("%-14s %5d %7.0f%% %7.2f %9s %8s" % (
            sym, st["n"], st["total"], st["t"],
            "%.2f" % sim if sim is not None else "-",
            "%+.2f" % (sim - st["t"]) if sim is not None else "-"))
        actualizar.escribir(actualizar.ESTADO, estado)

    estado["alertas"] = actualizar.alertas(estado)
    actualizar.escribir(actualizar.ESTADO, estado)
    print("\npágina actualizada: %s" % actualizar.render(estado))
    for a in estado["alertas"]:
        print("  %-12s %-12s %s" % (a["accion"].upper(), a["par"], a["por"]))


if __name__ == "__main__":
    main()
