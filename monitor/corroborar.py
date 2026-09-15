"""Mide pares desde exports de TradingView y acumula lo medido, export tras export.

El simulador de actualizar.py mira los 65 pares todos los meses sin que nadie
mueva un dedo, pero no puede reproducir el 2,8% de operaciones que nacen del
recálculo intravela de TradingView, y eso le deja el t más bajo —hasta 0,84 en
algún par—. Sirve para detectar movimiento, no para decidir.

Un export sí está en la misma escala que el informe. Así que el reparto es: el
simulador nomina, el export decide.

**Por qué se acumula.** TradingView tiene un límite de velas y su ventana se
desliza: hoy los exports de 4 horas arrancan en enero de 2022 —26 de los 65
pares empiezan exactamente ahí, BTC y ETH incluidos, que cotizan desde mucho
antes—, y dentro de un año van a arrancar en enero de 2023. Sin registro, cada
corroboración mediría una ventana distinta y perdería los años más difíciles.
Con registro, cada export aporta lo suyo, lo viejo queda guardado, y la historia
crece en vez de deslizarse.

Dos números salen de ese registro, y conviene mirar los dos: el **acumulado**,
que es el sólido, y el de los **últimos 18 meses**, que es el que se entera
cuando un par se apaga. Con cinco años adentro, un mes malo no mueve el
acumulado.

Uso:
    python monitor/corroborar.py
    python monitor/corroborar.py ruta/a/otra/carpeta
    python monitor/corroborar.py --rehacer     # descarta el registro previo
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
REGISTRO = os.path.join(AQUI, "corroboradas.json")
OFFSET = 3                      # los exports vienen en UTC-3
VENTANA_MESES = 18              # la mirada corta, la que detecta apagones
MINIMO_VENTANA = 12             # menos operaciones que esto y no se informa
TOLERANCIA = 0.01               # pp de diferencia que se acepta al reencontrar una operación


def huella():
    """Los parámetros con los que se midió. Mezclar lotes de estrategias distintas
    convertiría el registro en una suma de cosas que nunca existieron juntas."""
    salidas = []
    for r in simular.reglas():
        # Filtrar antes de ordenar: una regla puede tener atributos que no son
        # números —un nivel todavía en None— y ordenarlos mezclados explota.
        valores = [round(v, 4) for v in vars(r).values() if isinstance(v, (int, float))]
        salidas.append([r.name] + sorted(valores))
    return dict(salidas=sorted(salidas), tf=simular.FINE_TF, comision=simular.COMISION,
                desde=actualizar.MEDIR_DESDE.strftime("%Y-%m-%d"))


def archivos(carpeta):
    out = {}
    for f in sorted(glob.glob(os.path.join(carpeta, "*.csv"))):
        m = re.search(r"_([A-Z]+)_([A-Z0-9]+)\.P_", os.path.basename(f))
        if m and m.group(1) == "BINANCE":
            out[m.group(2)] = f
    return out


def medir(sym, path, proveedor):
    """Las operaciones del export, con las mismas reglas y costos que el informe."""
    trades = tradingview.read_trades(path, OFFSET)
    trades = [t for t in trades if t.entry_time >= actualizar.MEDIR_DESDE]
    if len(trades) < 2:
        return []
    res = estimate.run(trades, proveedor, sym, simular.FINE_TF,
                       simular.reglas(), simular.COMISION)
    llenas = [(t, f) for t, f in res.pairs if f is not None]
    if not llenas:
        return []
    fee = estimate.funding_cost([t for t, _f in llenas], proveedor, sym)
    paso = datetime.timedelta(seconds=candles.SECONDS[simular.FINE_TF])
    filas = []
    for (t, f), c in zip(llenas, fee):
        filas.append([t.entry_time.isoformat(), (t.entry_time + paso * f.bars).isoformat(),
                      round(f.pct - c, 5), t.long, f.signal])
    return filas


def fusionar(previas, nuevas, archivo, hoy):
    """Une lo nuevo con lo guardado, sin pisar nada y avisando si algo no coincide.

    La clave es el momento de entrada. Los exports se superponen a propósito, y
    esa superposición es un control gratis: una operación que ya conocíamos tiene
    que volver con el mismo resultado. Si vuelve distinta, algo cambió —los
    parámetros del gráfico, los datos del exchange— y eso hay que verlo, no
    promediarlo.
    """
    porclave = {(o[0], o[3]): o for o in previas}
    agregadas = repetidas = 0
    choques = []
    for o in nuevas:
        clave = (o[0], o[3])
        vieja = porclave.get(clave)
        if vieja is None:
            porclave[clave] = o
            agregadas += 1
            continue
        repetidas += 1
        if abs(vieja[2] - o[2]) > TOLERANCIA:
            choques.append((o[0], vieja[2], o[2]))
    ops = sorted(porclave.values(), key=lambda o: o[0])
    lote = dict(archivo=os.path.basename(archivo), medido=hoy, aporto=agregadas,
                repetidas=repetidas, desde=nuevas[0][0][:7], hasta=nuevas[-1][1][:7])
    return ops, lote, choques


def estadisticas(ops, desde=None):
    rets = [o[2] for o in ops if desde is None or o[0] >= desde]
    if len(rets) < 2:
        return None
    sd = statistics.pstdev(rets)
    return dict(n=len(rets), total=round(sum(rets), 1),
                t=round(statistics.mean(rets) / (sd / math.sqrt(len(rets))), 3) if sd else 0.0)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    carpeta = args[0] if args else CARPETA
    if not os.path.isdir(carpeta):
        sys.exit("No existe %s. Dejá ahí los exports de 'List of Trades'." % carpeta)
    encontrados = archivos(carpeta)
    if not encontrados:
        sys.exit("No hay CSV de Binance en %s." % carpeta)

    estado = actualizar.leer(actualizar.ESTADO, None)
    if estado is None:
        sys.exit("Todavía no hay estado.json. Corré antes monitor/actualizar.py.")

    registro = {} if "--rehacer" in sys.argv else actualizar.leer(REGISTRO, {})
    if registro.get("parametros") and registro["parametros"] != huella():
        sys.exit("El registro se armó con otros parámetros de estrategia:\n  guardado %s\n  ahora    %s\n"
                 "Las operaciones viejas describen otra estrategia. Volvé a los parámetros\n"
                 "anteriores, o rehacé el registro con --rehacer y exports nuevos."
                 % (registro["parametros"], huella()))
    registro["parametros"] = huella()
    registro.setdefault("pares", {})

    proveedor = candles.get_provider("binance")
    hoy = datetime.date.today().isoformat()
    corte = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=VENTANA_MESES * 30.44)).isoformat()

    print("corroborando %d pares | registro con %d pares guardados\n"
          % (len(encontrados), len(registro["pares"])))
    print("%-14s %6s %6s %8s %7s %9s %8s" % (
        "par", "nuevas", "repet.", "acumulado", "t acum", "t 18 meses", "t simulado"))
    for sym in sorted(encontrados):
        try:
            nuevas = medir(sym, encontrados[sym], proveedor)
        except Exception as exc:
            print("%-14s ERROR %s: %s" % (sym, type(exc).__name__, exc))
            continue
        if not nuevas:
            print("%-14s sin operaciones suficientes" % sym)
            continue
        guardado = registro["pares"].setdefault(sym, {"ops": [], "lotes": []})
        ops, lote, choques = fusionar(guardado["ops"], nuevas, encontrados[sym], hoy)
        guardado["ops"] = ops
        guardado["lotes"] = [l for l in guardado["lotes"] if l["archivo"] != lote["archivo"]] + [lote]

        acum = estadisticas(ops)
        corto = estadisticas(ops, corte)
        if corto and corto["n"] < MINIMO_VENTANA:
            corto = None
        fila = estado["pares"].setdefault(sym, {})
        fila["corroborado"] = dict(
            n=acum["n"], total=acum["total"], t=acum["t"],
            t18=corto["t"] if corto else None, n18=corto["n"] if corto else None,
            desde=ops[0][0][:7], hasta=ops[-1][1][:7], medido=hoy, lotes=len(guardado["lotes"]))
        sim = fila.get("t")
        print("%-14s %6d %6d %8d %7.2f %9s %8s" % (
            sym, lote["aporto"], lote["repetidas"], acum["n"], acum["t"],
            "%.2f (%d)" % (corto["t"], corto["n"]) if corto else "-",
            "%.2f" % sim if sim is not None else "-"))
        for momento, antes, ahora in choques:
            print("       CHOQUE en %s: guardado %+.2f%%, ahora %+.2f%%" % (momento, antes, ahora))
        actualizar.escribir(REGISTRO, registro)
        actualizar.escribir(actualizar.ESTADO, estado)

    estado["alertas"] = actualizar.alertas(estado)
    actualizar.escribir(actualizar.ESTADO, estado)
    print("\npágina actualizada: %s" % actualizar.render(estado))
    for a in estado["alertas"]:
        print("  %-11s %-12s %s" % (a["accion"].upper(), a["par"], a["por"]))


if __name__ == "__main__":
    main()
