"""Las señales de la estrategia, reimplementadas desde strategy.pine.

El motor de replay re-recorre operaciones que ya existen: no inventa entradas.
Para que el monitoreo mensual se actualice solo hace falta generar las señales
acá, desde las velas, en vez de esperar un export de TradingView.

Esto es una traducción línea por línea de la sección de divergencias del Pine,
no una interpretación de la idea. Lo que la valida está en validar_senales.py:
los 70 exports que ya tenemos sirven de conjunto de prueba, y cubre el 97,1%
de las entradas que TradingView tomó.

Dos convenciones de TradingView que importan:

- La señal se evalúa al cierre de la vela y la orden se ejecuta en la apertura
  de la siguiente. Una señal en la vela i produce una entrada en la vela i+1.
- Con calc_on_order_fills la estrategia vuelve a evaluarse apenas se llena una
  orden, en medio de la vela. En ese momento `close` no es el cierre de la vela
  sino el precio del instante, así que la condición puede dar distinto. Para eso
  está Motor.intravela(): el 2,8% de las operaciones nace de esa reevaluación, y
  omitirlas costaba entre 16 y 41 puntos de rendimiento por par.
"""
import collections

#: Parámetros de strategy.pine. No son configurables acá a propósito: si el
#: Pine cambia, esto tiene que cambiar con él y volver a validarse.
RSI_LEN = 8
OB = 72
OS = 28
LOOKBACK = 60
OBOS_ONLY = True
ALLOW_BULL = True
ALLOW_BEAR = True

Senal = collections.namedtuple("Senal", "index time long")


def _rsi(au, ad):
    if ad == 0:
        return 100.0
    if au == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + au / ad)


def _wilder(closes, length):
    """RSI de Wilder junto con las medias que lo sostienen.

    ta.rma() es una media exponencial con alpha = 1/length sembrada con la
    media simple de los primeros `length` valores. Sembrarla con el primer
    valor en vez de la media corre el RSI durante decenas de velas.

    Devuelve (rsi, au, ad) alineados con `closes`; las medias hacen falta para
    poder recalcular el RSI de una vela con un precio distinto al cierre.
    """
    n = len(closes)
    r, au, ad = [None] * n, [None] * n, [None] * n
    if n <= length:
        return r, au, ad
    subas, bajas = [], []
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        subas.append(d if d > 0 else 0.0)
        bajas.append(-d if d < 0 else 0.0)
    u = sum(subas[:length]) / length
    d_ = sum(bajas[:length]) / length
    r[length], au[length], ad[length] = _rsi(u, d_), u, d_
    for i in range(length, len(subas)):
        u = (u * (length - 1) + subas[i]) / length
        d_ = (d_ * (length - 1) + bajas[i]) / length
        r[i + 1], au[i + 1], ad[i + 1] = _rsi(u, d_), u, d_
    return r, au, ad


def rsi(closes, length=RSI_LEN):
    """RSI de Wilder, igual que ta.rsi(). None donde el Pine daría na."""
    return _wilder(closes, length)[0]


def _barras_desde_extremo(valores, length, mayor):
    """Equivalente a abs(ta.highestbars()) y abs(ta.lowestbars()).

    Cuántas velas atrás está el máximo (o el mínimo) de la ventana. Cero
    significa que el extremo es la vela actual, que es lo que el Pine usa
    para reiniciar el swing.

    Cola monótona para no recorrer la ventana en cada vela: con 65 pares y
    cinco años de historia la versión ingenua tarda minutos. Ante valores
    iguales gana el más reciente, igual que la función de Pine.
    """
    out = [None] * len(valores)
    cola = collections.deque()
    for i, v in enumerate(valores):
        if v is None:
            cola.clear()
            continue
        while cola and (valores[cola[-1]] <= v if mayor else valores[cola[-1]] >= v):
            cola.pop()
        cola.append(i)
        while cola[0] <= i - length:
            cola.popleft()
        out[i] = i - cola[0]
    return out


class Motor(object):
    """El estado que la divergencia necesita, vela por vela.

    Guarda las series que el Pine mantiene con `var` —el extremo de precio y
    de RSI vigentes— porque la condición mira los valores de velas anteriores,
    no solo el corriente.
    """

    def __init__(self, velas):
        self.velas = velas
        self.closes = [c.close for c in velas]
        self.r, self.au, self.ad = _wilder(self.closes, RSI_LEN)
        self.hb = _barras_desde_extremo(self.r, LOOKBACK, True)
        self.lb = _barras_desde_extremo(self.r, LOOKBACK, False)
        self.max_price, self.max_rsi = [], []
        self.min_price, self.min_rsi = [], []
        for i, c in enumerate(velas):
            if self.r[i] is None:
                for serie in (self.max_price, self.max_rsi, self.min_price, self.min_rsi):
                    serie.append(None)
                continue
            mp, mr, np_, nr = self._extremos(i, c.close, self.r[i], self.hb[i] == 0, self.lb[i] == 0)
            self.max_price.append(mp)
            self.max_rsi.append(mr)
            self.min_price.append(np_)
            self.min_rsi.append(nr)

    def _extremos(self, i, precio, valor, reinicia_max, reinicia_min):
        """El bloque de swing detection del Pine, para una vela.

            maxPrice := hb == 0 ? close : na(maxPrice[1]) ? close : maxPrice[1]
            if close > maxPrice
                maxPrice := close
        """
        previo = i - 1
        anterior_mp = self.max_price[previo] if previo >= 0 and previo < len(self.max_price) else None
        anterior_mr = self.max_rsi[previo] if previo >= 0 and previo < len(self.max_rsi) else None
        anterior_np = self.min_price[previo] if previo >= 0 and previo < len(self.min_price) else None
        anterior_nr = self.min_rsi[previo] if previo >= 0 and previo < len(self.min_rsi) else None
        mp = precio if reinicia_max or anterior_mp is None else anterior_mp
        mr = valor if reinicia_max or anterior_mr is None else anterior_mr
        np_ = precio if reinicia_min or anterior_np is None else anterior_np
        nr = valor if reinicia_min or anterior_nr is None else anterior_nr
        if precio > mp:
            mp = precio
        if valor > mr:
            mr = valor
        if precio < np_:
            np_ = precio
        if valor < nr:
            nr = valor
        return mp, mr, np_, nr

    def _condicion(self, i, valor, max_rsi, min_rsi):
        """bearDiv y bullDiv del Pine. Devuelve True (largo), False (corto) o None.

            bearDiv = allowBear and (maxPrice[1] > maxPrice[2]) and (rsi[1] < maxRsi)
                      and (rsi <= rsi[1]) and (not obosOnly or maxRsi >= ob)

        `maxPrice[1]` y `[2]` son los valores de velas anteriores, ya cerradas,
        así que se leen de las series y no dependen del precio del instante.
        """
        if i < 2 or self.r[i - 1] is None or self.max_price[i - 2] is None:
            return None
        previo = self.r[i - 1]
        bear = (ALLOW_BEAR and self.max_price[i - 1] > self.max_price[i - 2]
                and previo < max_rsi and valor <= previo
                and (not OBOS_ONLY or max_rsi >= OB))
        bull = (ALLOW_BULL and self.min_price[i - 1] < self.min_price[i - 2]
                and previo > min_rsi and valor >= previo
                and (not OBOS_ONLY or min_rsi <= OS))
        # El Pine evalúa primero el largo: `if longSignal ... else if shortSignal`.
        if bull:
            return True
        if bear:
            return False
        return None

    def senales(self):
        """Las señales al cierre de cada vela, que es el caso normal."""
        out = []
        for i, c in enumerate(self.velas):
            if self.r[i] is None:
                continue
            largo = self._condicion(i, self.r[i], self.max_rsi[i], self.min_rsi[i])
            if largo is not None:
                out.append(Senal(i, c.time, largo))
        return out

    def intravela(self, i, precio):
        """La condición evaluada en medio de la vela `i`, con `precio` como cierre.

        Es lo que ve Pine cuando recalcula al llenarse una orden: el RSI se
        recalcula con el precio del instante, y con él los extremos vigentes.
        Devuelve True (largo), False (corto) o None.
        """
        if i < 2 or i >= len(self.velas) or self.au[i - 1] is None:
            return None
        cambio = precio - self.closes[i - 1]
        u = (self.au[i - 1] * (RSI_LEN - 1) + (cambio if cambio > 0 else 0.0)) / RSI_LEN
        d = (self.ad[i - 1] * (RSI_LEN - 1) + (-cambio if cambio < 0 else 0.0)) / RSI_LEN
        valor = _rsi(u, d)
        # hb == 0 / lb == 0 con el RSI del instante: ante empate gana el más
        # reciente, que es esta misma vela.
        desde = max(0, i - LOOKBACK + 1)
        previos = [v for v in self.r[desde:i] if v is not None]
        reinicia_max = not previos or valor >= max(previos)
        reinicia_min = not previos or valor <= min(previos)
        _mp, mr, _np, nr = self._extremos(i, precio, valor, reinicia_max, reinicia_min)
        return self._condicion(i, valor, mr, nr)


def divergencias(velas):
    """Las señales de divergencia al cierre de cada vela."""
    return Motor(velas).senales()
