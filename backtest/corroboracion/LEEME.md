# Exports para corroborar

Acá van los CSV de **List of Trades** que exportes de TradingView cuando quieras
confirmar un par en la escala del informe. Después:

```bash
python monitor/corroborar.py
```

El script los mide con las mismas reglas, resolución y costos que el informe, y
deja el resultado al lado del número simulado en la página del monitor.

**No hace falta exportar los 65.** Alcanza con los de la cartera y los que el
monitor haya señalado con "exportar y mirar": diez o quince archivos.

Antes de exportar, verificá que el gráfico tenga los parámetros de
[`../../strategy.pine`](../../strategy.pine): 4 horas, sin toma de ganancias,
stop 5,0 y trailing 3,0 con offset 0,6. Un export con otros parámetros entra sin
protestar y contamina la comparación.

Los CSV están ignorados por git; este archivo existe para que la carpeta viaje
con el repo.
