"""Recalcula el estado de cada par y avisa quién cruzó el umbral.

Pensado para correr una vez por mes. No necesita exports de TradingView: las
entradas las genera senales.py y las salidas las resuelve el replay contra
velas reales, así que lo único que hace falta es conexión.

Una regla que no se negocia: **este monitor compara consigo mismo**. Sus
números no son intercambiables con los del informe, que salen de los exports de
TradingView. Las operaciones que las dos vías comparten dan idéntico, pero el
simulador no puede generar el 2,8% que nace del recálculo intravela de
TradingView, y ese faltante deja el t entre 0,1 y 0,7 más bajo según el par.
Comparar una lectura de acá contra una del informe daría una alarma falsa;
comparar las de acá entre meses, no. Ver README.md.

El umbral tiene margen y memoria a propósito. Un corte seco en t = 2 haría
entrar y salir pares por ruido de una sola operación, así que hace falta cruzar
1,8 o 2,2 y sostenerlo dos lecturas seguidas.

Uso:
    python monitor/actualizar.py                  # todos los pares
    python monitor/actualizar.py AAVE SFP         # algunos
    python monitor/actualizar.py --reconstruir    # descarta la historia previa
"""
import collections
import datetime
import io
import json
import math
import os
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BME = os.environ.get("BME_PATH") or os.path.join(os.path.dirname(RAIZ), "bar-magnifier-estimator")
if not os.path.isdir(BME):
    sys.exit("No encuentro bar-magnifier-estimator en %s. Cloná el repo al lado de este,\n"
             "o apuntá BME_PATH a donde esté." % BME)
sys.path.insert(0, BME)
sys.path.insert(0, AQUI)

from bme import candles, estimate                 # noqa: E402
import simular                                    # noqa: E402

PARES = os.path.join(AQUI, "pares.txt")
ESTADO = os.path.join(AQUI, "estado.json")
OPERACIONES = os.path.join(AQUI, "operaciones.json")
PLANTILLA = os.path.join(AQUI, "plantilla.html")
PAGINA = os.path.join(RAIZ, "informe", "monitor.html")
INICIO = datetime.datetime(2021, 9, 1, tzinfo=datetime.timezone.utc)
#: Desde cuándo cuentan las operaciones. Las velas anteriores son calentamiento
#: del RSI y de los extremos del swing, nada más.
#:
#: El corte no es capricho: los últimos meses de 2021 contienen el techo del
#: ciclo, y ahí unas pocas decenas de operaciones producen más que los cuatro
#: años siguientes juntos. Midiendo desde 2021, ZEC daba 619% con t 2,60 y
#: entraba como candidato; midiendo desde 2022 da -23% con t -0,29. La ventana
#: también es la de los exports, así que las dos vías quedan comparables.
MEDIR_DESDE = datetime.datetime(2022, 1, 1, tzinfo=datetime.timezone.utc)
UMBRAL = 2.0
MARGEN_BAJO, MARGEN_ALTO = 1.8, 2.2
PERSISTENCIA = 2                # lecturas seguidas del mismo lado para avisar
PASO = datetime.timedelta(hours=4)

#: funding_cost espera entry_time / exit_time / long.
_Adaptada = collections.namedtuple("_Adaptada", "entry_time exit_time long")


def universo():
    out = []
    for linea in io.open(PARES, encoding="utf-8"):
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            out.append(linea)
    return out


def leer(path, defecto):
    if not os.path.exists(path):
        return defecto
    return json.load(io.open(path, encoding="utf-8"))


def escribir(path, datos):
    json.dump(datos, io.open(path, "w", encoding="utf-8"), separators=(",", ":"))


def render(estado):
    """Vuelca el estado dentro de la plantilla y deja la página lista.

    Los datos van embebidos en el HTML en vez de cargarse aparte: así la página
    se puede abrir desde el disco, mandar por mail o publicar sin arrastrar un
    JSON al lado.
    """
    plantilla = io.open(PLANTILLA, encoding="utf-8").read()
    html = plantilla.replace("__DATA__", json.dumps(estado, separators=(",", ":")))
    if "__DATA__" in html:
        raise RuntimeError("la plantilla no tiene marcador __DATA__")
    io.open(PAGINA, "w", encoding="utf-8", newline="\n").write(html)
    return PAGINA


def estadisticas(ops):
    """Las mismas medidas que usa el informe, sobre las operaciones propias."""
    rets = [o.ret for o in ops]
    if len(rets) < 2:
        return None
    eq = peak = 1.0
    mdd = 0.0
    for x in rets:
        eq *= 1 + x / 100.0
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    anios = (ops[-1].salida - ops[0].entrada).total_seconds() / 31557600.0
    sd = statistics.pstdev(rets)
    return dict(n=len(rets), total=round(sum(rets), 1),
                t=round(statistics.mean(rets) / (sd / math.sqrt(len(rets))), 3) if sd else 0.0,
                cagr=round(100 * (eq ** (1 / anios) - 1), 1) if eq > 0 and anios > 0 else None,
                mdd=round(100 * mdd, 1),
                desde=ops[0].entrada.strftime("%Y-%m"), hasta=ops[-1].salida.strftime("%Y-%m"))


def medir(sym, proveedor, hasta):
    """Simula el par entero y devuelve (estadisticas, operaciones)."""
    velas = proveedor.series(sym, simular.CHART_TF, INICIO, hasta).candles
    if len(velas) < simular.CALENTAMIENTO:
        return None, []
    fina = proveedor.series(sym, simular.FINE_TF, INICIO + PASO * simular.CALENTAMIENTO, hasta)
    ops = [o for o in simular.operaciones(velas, fina) if o.entrada >= MEDIR_DESDE]
    if not ops:
        return None, []
    fee = estimate.funding_cost([_Adaptada(o.entrada, o.salida, o.largo) for o in ops],
                                proveedor, sym)
    for o, f in zip(ops, fee):
        o.ret -= f
    return estadisticas(ops), ops


def lado(t):
    """Arriba, abajo, o en la banda donde no se decide nada."""
    if t is None:
        return None
    if t >= MARGEN_ALTO:
        return "arriba"
    if t <= MARGEN_BAJO:
        return "abajo"
    return None


#: Después de cuántos meses una corroboración deja de valer. Una estrategia de
#: 4 horas suma entre cinco y ocho operaciones por par por mes, así que medio
#: año es material nuevo suficiente como para volver a mirar.
VENCE = 6

#: La ventana corta que mira corroborar.py, solo para redactar los avisos.
VENTANA_CORTA = 18


def _vieja(medido, ultimo_mes):
    """¿La corroboración quedó atrás en el tiempo?"""
    if not medido:
        return True
    a, m = int(medido[:4]), int(medido[5:7])
    b, n = int(ultimo_mes[:4]), int(ultimo_mes[5:7])
    return (b * 12 + n) - (a * 12 + m) >= VENCE


def alertas(estado):
    """Qué hacer con cada par, separando quién nomina de quién decide.

    El simulador no puede decidir: su t corre entre 0,1 y 0,8 por debajo del
    que produce un export, y la cartera se definió con exports. Lo que sí puede
    es *nominar* — avisar que un par se movió lo suficiente como para que valga
    la pena exportarlo y mirarlo en serio.

    Así que hay dos clases de aviso:

      corroborar   el simulado sostuvo un cruce que contradice a la cartera.
                   Exportá ese par de TradingView y pasalo por corroborar.py.
      quitar/agregar   ya hay un export reciente y dice lo mismo. Eso sí es
                   una decisión, porque está en la escala del informe.
    """
    pool = estado.get("pool", [])
    out = []
    meses = [l[-1]["m"] for l in estado.get("historia", {}).values() if l]
    mes_ref = max(meses) if meses else datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m")

    # El acumulado tarda en enterarse: con cinco años adentro, un año malo casi
    # no lo mueve. Si la ventana corta se apagó mientras el acumulado todavía
    # sostiene al par, eso no decide nada, pero no puede pasar desapercibido.
    #
    # Esta señal sale del registro de exports, que trae su propia muestra, así
    # que no espera las dos lecturas mensuales que piden los demás avisos.
    for sym in sorted(pool):
        corr = (estado.get("pares", {}).get(sym) or {}).get("corroborado")
        if not corr or _vieja(corr.get("medido"), mes_ref):
            continue
        # Alcanza con que el acumulado no lo esté condenando ya: si cayó por
        # debajo de la banda, de eso se encarga el aviso de sacarlo. Exigir que
        # estuviera arriba de 2,2 dejaba afuera justo a los que tienen el
        # acumulado en la banda y la ventana corta apagada.
        if corr["t"] > MARGEN_BAJO and corr.get("t18") is not None and corr["t18"] <= MARGEN_BAJO:
            out.append(dict(par=sym, accion="vigilar", t=corr["t18"], fuente="export",
                            desde=corr.get("desde", ""), meses=VENTANA_CORTA,
                            por="el acumulado lo sostiene con t de %.2f, pero en los últimos "
                                "%d meses cae a %.2f sobre %d operaciones."
                                % (corr["t"], VENTANA_CORTA, corr["t18"], corr["n18"])))

    for sym, lecturas in sorted(estado.get("historia", {}).items()):
        ultimas = lecturas[-PERSISTENCIA:]
        if len(ultimas) < PERSISTENCIA:
            continue
        lados = [lado(x["t"]) for x in ultimas]
        if lados[0] is None or len(set(lados)) != 1:
            continue
        actual, dentro = lados[0], sym in pool
        corr = (estado.get("pares", {}).get(sym) or {}).get("corroborado")
        fresca = corr and not _vieja(corr.get("medido"), ultimas[-1]["m"])

        if (actual == "abajo") != dentro:
            continue                    # el simulado coincide con la cartera
        if fresca:
            if dentro and corr["t"] <= MARGEN_BAJO:
                out.append(dict(par=sym, accion="quitar", t=corr["t"], fuente="export",
                                desde=ultimas[0]["m"], meses=len(ultimas),
                                por="el export lo confirma: t de %.2f, medido el %s"
                                    % (corr["t"], corr["medido"])))
            elif not dentro and corr["t"] >= MARGEN_ALTO:
                out.append(dict(par=sym, accion="agregar", t=corr["t"], fuente="export",
                                desde=ultimas[0]["m"], meses=len(ultimas),
                                por="el export lo confirma: t de %.2f, medido el %s"
                                    % (corr["t"], corr["medido"])))
            continue                    # el export ya se pronunció
        out.append(dict(par=sym, accion="corroborar", t=ultimas[-1]["t"], fuente="simulado",
                        desde=ultimas[0]["m"], meses=len(ultimas),
                        por="el simulado marca %.2f desde %s, %s la cartera. Exportalo de "
                            "TradingView para medirlo en la escala del informe."
                            % (ultimas[-1]["t"], ultimas[0]["m"],
                               "estando en" if dentro else "estando afuera de")))
    return out


def main():
    # La corrida mensual dura horas y se agenda redirigida a un log. Sin esto
    # Python bufferea la salida y el log queda vacío hasta que el proceso
    # termina, que es justo cuando ya no sirve para saber cómo viene.
    sys.stdout.reconfigure(line_buffering=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    reconstruir = "--reconstruir" in sys.argv
    estado = dict(tf=simular.FINE_TF, generado=None, pares={}, historia={}, pool=[], alertas=[])
    if not reconstruir:
        estado.update(leer(ESTADO, {}))
    estado.setdefault("pool", [])
    estado.setdefault("historia", {})
    estado.setdefault("pares", {})

    todos = universo()
    elegidos = [a if a.endswith("USDT") else a + "USDT" for a in args] if args else todos
    ahora = datetime.datetime.now(datetime.timezone.utc)
    mes = ahora.strftime("%Y-%m")
    proveedor = candles.get_provider("binance")
    guardadas = leer(OPERACIONES, {}) if not reconstruir else {}

    print("monitoreo a %s | %d pares | %s\n" % (simular.FINE_TF, len(elegidos), mes))
    print("%-14s %5s %8s %7s %8s %7s %s" % ("par", "ops", "total", "t", "anual", "caida", "cambio"))
    for sym in elegidos:
        try:
            st, ops = medir(sym, proveedor, ahora)
        except Exception as exc:
            print("%-14s ERROR %s: %s" % (sym, type(exc).__name__, exc))
            continue
        if st is None:
            print("%-14s sin historia suficiente" % sym)
            continue
        previo = estado["pares"].get(sym, {}).get("t")
        estado["pares"][sym] = st
        serie = estado["historia"].setdefault(sym, [])
        if serie and serie[-1]["m"] == mes:
            serie[-1] = dict(m=mes, t=st["t"], n=st["n"], total=st["total"])
        else:
            serie.append(dict(m=mes, t=st["t"], n=st["n"], total=st["total"]))
        guardadas[sym] = [o.fila() for o in ops]
        print("%-14s %5d %7.0f%% %7.2f %7.1f%% %6.1f%% %s" % (
            sym, st["n"], st["total"], st["t"],
            st["cagr"] if st["cagr"] is not None else float("nan"), st["mdd"],
            "" if previo is None else "%+.2f" % (st["t"] - previo)))
        escribir(ESTADO, estado)
        escribir(OPERACIONES, guardadas)

    estado["generado"] = ahora.strftime("%Y-%m-%d")
    estado["alertas"] = alertas(estado)
    escribir(ESTADO, estado)
    escribir(OPERACIONES, guardadas)

    print("\npool actual: %s" % (", ".join(estado["pool"]) or "sin definir (editar estado.json)"))
    if not estado["alertas"]:
        print("sin cambios que avisar")
    for a in estado["alertas"]:
        print("  %-11s %-12s %s" % (a["accion"].upper(), a["par"], a["por"]))
    print("\npagina actualizada: %s" % render(estado))


if __name__ == "__main__":
    main()
