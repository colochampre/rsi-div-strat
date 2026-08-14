# Análisis de backtests

Scripts para validar exports de TradingView de la estrategia. Requieren Python 3
y los CSV de la lista de operaciones en `../backtest/`.

> **Importante:** `backtest/*.csv` está en `.gitignore`. Los exports no viajan con
> el repositorio: hay que volver a generarlos desde TradingView en cada máquina.

Formato esperado: export de la pestaña "List of Trades", dos filas por operación
(entrada y salida), con las columnas `Signal`, `Return %`, `Favorable excursion %`,
`Adverse excursion %` y `Duration (bars)`.

Nomenclatura de archivos: `<SIMBOLO>USDT.P_<TF>_<activacion>-<offset>_<fecha>.csv`
(ejemplo: `ETHUSDT.P_4h_1.0-0.5_2026-08-14.csv`). Los scripts descubren los
archivos por glob, así que el nombre importa.

## Scripts

| Script | Pregunta que responde |
|---|---|
| `oos.py` | ¿La estrategia funciona fuera del símbolo donde se ajustaron los parámetros? Config inferida de los datos, resultado por símbolo, piso, ambigüedad y slippage. |
| `regimen.py` | ¿El resultado está repartido entre regímenes o concentrado en uno? Desglose por año, relación con la volatilidad y correlación entre símbolos. |
| `pareado.py` | Comparación pareada de dos configuraciones sobre los mismos símbolos, con control de validez y descomposición del delta. |
| `fiabilidad.py` | ¿Cuánto del resultado depende del orden de recorrido que asume el emulador? Incluye la cota pesimista. |

Todos se ejecutan sin argumentos: `python analysis/oos.py`

## Métricas propias

**Config inferida.** Los scripts deducen SL, TP y offset desde los propios datos
en lugar de confiar en el nombre del archivo. Sirve para detectar exports con
parámetros distintos a los esperados.

**Piso.** El peor resultado posible de una salida por trailing es
`activación − offset − comisión`. Si el peor valor observado no coincide con ese
número, algo no cuadra entre la configuración y el export.

**Ambigüedad de orden.** El emulador conoce el máximo y el mínimo reales de cada
vela, pero asume en qué orden se recorrieron. Una operación es ambigua cuando
dentro de su recorrido eran alcanzables tanto la salida ganadora como el stop
loss: ahí el signo del resultado lo decide una suposición.

**Cota pesimista.** Fuerza toda operación ambigua a stop loss completo y cobra
slippage en cada salida por trailing. Es la métrica que indica si el resultado se
sostiene sin `use_bar_magnifier`.
