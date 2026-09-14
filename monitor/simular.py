"""La estrategia completa sin TradingView: señales propias y salidas replayadas.

senales.py dice cuándo la estrategia querría operar. Acá se decide cuándo
efectivamente opera —TradingView ignora una señal si ya hay posición abierta—
y qué le pasa a cada operación, recorriendo velas finas con las mismas reglas
de salida que usa el informe.

El resultado tiene la misma forma que el de un export procesado: entrada,
salida, retorno y motivo. De ahí en más el resto del análisis no distingue si
las operaciones vinieron de un CSV de TradingView o de acá.

Tres detalles que no son adorno, los tres medidos contra los 65 exports:

- La orden se ejecuta en la apertura de la vela siguiente a la señal. Es el
  98,8% de las entradas: llenan exactamente en esa apertura.
- Con calc_on_order_fills la estrategia se reevalúa apenas se llena una orden,
  en medio de la vela, y el `close` que ve es el precio de ese instante. De ahí
  nace el 2,8% restante de las operaciones.
- Esas reentradas no llenan en la apertura: llenan en el extremo de la vela en
  la dirección de la salida —un largo que sale por stop deja el precio en el
  mínimo, un corto en el máximo—. Se cumple en el 94,9% de los casos. Entrar al
  precio equivocado cuesta más que no entrar: las operaciones extra terminaban
  negativas y arrastraban toda la secuencia posterior.
"""
import datetime
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
BME = os.environ.get("BME_PATH") or os.path.join(os.path.dirname(os.path.dirname(AQUI)),
                                                 "bar-magnifier-estimator")
if os.path.isdir(BME) and BME not in sys.path:
    sys.path.insert(0, BME)
sys.path.insert(0, AQUI)

from bme import engine, rules                   # noqa: E402
from bme.candles import SECONDS                 # noqa: E402
import senales                                  # noqa: E402

CHART_TF = "4h"
FINE_TF = "5m"
COMISION = 0.1                  # 0.05% por lado
MAX_HORAS = 240
CALENTAMIENTO = 500             # velas de 4h antes del primer resultado utilizable
MAX_CADENA = 50                 # tope de reentradas encadenadas dentro de una vela


def reglas():
    """Las salidas de strategy.pine, de la más ajustada a la más ancha."""
    return [rules.TrailingStop(activation=3.0, offset=0.6), rules.StopLoss(5.0)]


class Operacion(object):
    __slots__ = ("entrada", "salida", "ret", "largo", "motivo", "precio")

    def __init__(self, entrada, salida, ret, largo, motivo, precio):
        self.entrada, self.salida, self.ret = entrada, salida, ret
        self.largo, self.motivo, self.precio = largo, motivo, precio

    def fila(self):
        return [self.entrada.isoformat(), self.salida.isoformat(), round(self.ret, 5),
                self.largo, self.motivo]


def _utc(ms):
    return datetime.datetime.fromtimestamp(ms / 1000.0, datetime.timezone.utc)


def operaciones(velas_chart, serie_fina, comision=COMISION, reentrada_intravela=True,
                fine_tf=FINE_TF):
    """Recorre las señales con estado de posición y devuelve las operaciones.

    `velas_chart` son las velas del gráfico (4h) con su calentamiento incluido;
    `serie_fina` es la CandleSeries donde se resuelven las salidas, y `fine_tf`
    su granularidad. Las operaciones que no alcanzan a cerrar dentro del
    horizonte se descartan: una posición abierta no es un resultado.

    Validar contra un export pide `fine_tf="4h"`, que es la resolución con la
    que TradingView produjo ese export; estimar la realidad pide la más fina que
    se pueda pagar. Son la misma simulación con distinta lupa.
    """
    if not velas_chart:
        return []
    motor = senales.Motor(velas_chart)
    por_vela = {}
    for s in motor.senales():
        por_vela.setdefault(s.index, s)

    paso_chart = SECONDS[CHART_TF]
    paso_fino = datetime.timedelta(seconds=SECONDS[fine_tf])
    max_barras = max(2, int(MAX_HORAS * 3600 / SECONDS[fine_tf]))
    inicio = _utc(velas_chart[0].time)

    def vela_de(momento):
        j = int((momento - inicio).total_seconds() // paso_chart)
        return min(max(j, 0), len(velas_chart) - 1)

    out = []
    libre = 0                   # primera vela de chart en la que se puede entrar
    for indice in sorted(por_vela):
        i = indice + 1          # la orden se llena en la vela siguiente
        if i >= len(velas_chart) or i < libre:
            continue
        largo = por_vela[indice].long
        entrada = _utc(velas_chart[i].time)
        precio = velas_chart[i].open
        desde = entrada
        for _ in range(MAX_CADENA):
            ventana = serie_fina.window(desde, max_barras)
            if not ventana:
                break
            fill = engine.replay(precio, largo, ventana, reglas(), comision)
            if fill is None:
                break           # sigue abierta al final de la historia
            salida = desde + paso_fino * fill.bars
            out.append(Operacion(entrada, salida, fill.pct, largo, fill.signal, precio))
            j = vela_de(salida)
            libre = j + 1
            if not reentrada_intravela:
                break
            # La posición se cerró dentro de la vela j y el precio quedó en el
            # extremo que disparó la salida. Ahí la estrategia se reevalúa.
            extremo = velas_chart[j].low if largo else velas_chart[j].high
            nueva = motor.intravela(j, extremo)
            if nueva is None:
                break
            largo = nueva
            entrada = _utc(velas_chart[j].time)   # el export estampa la vela, no el instante
            precio = extremo
            desde = salida + paso_fino
    return out
