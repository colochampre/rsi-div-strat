# Monitoreo mensual

Recalcula el rendimiento de cada par del universo y avisa cuándo alguno cruza el
umbral de ventaja estadística, para sumarlo o sacarlo de la cartera.

No hace falta exportar nada de TradingView. Las entradas las genera
[`senales.py`](senales.py), que es la lógica de divergencia de
[`../strategy.pine`](../strategy.pine) traducida a Python, y las salidas las
resuelve el motor de replay contra velas reales de Binance.

```bash
python monitor/actualizar.py                  # todos los pares
python monitor/actualizar.py AAVE SFP         # algunos
python monitor/actualizar.py --reconstruir    # descarta la historia previa
```

Requiere Python 3 y [bar-magnifier-estimator](https://github.com/colochampre/bar-magnifier-estimator)
clonado al lado de este repo, o `BME_PATH` apuntando a él.

---

## Lo primero: uno nomina, el otro decide

El simulador mira los 65 pares todos los meses sin que nadie mueva un dedo, pero
sus números **no son intercambiables** con los del informe, que salen de los
exports de TradingView. Mezclarlos produce alarmas falsas. El motivo está
medido:

| | |
|---|---|
| entradas de TradingView que la reimplementación reproduce | 97,1% (15.588 de 16.052) |
| diferencia de retorno en las operaciones que ambas toman | 0,0000 pp |
| señales sobrantes sin explicación | 13 en 65 pares |
| operaciones que TradingView toma y acá no aparecen | 2,8% |

Ese 2,8% nace del recálculo intravela de TradingView: con
`calc_on_order_fills`, cuando un stop se ejecuta en medio de una vela la
estrategia se reevalúa ahí mismo, con el precio de ese instante como `close`.
Reproducirlo exigiría simular el orden de los eventos dentro de la vela, que es
justamente lo que un backtest no puede saber — el mismo límite que documenta la
auditoría del Bar Magnifier. Como esas operaciones resultaron rentables, su
ausencia deja el `t` de cada par entre 0,1 y 0,7 más bajo que el del informe.

Un termómetro que lee medio grado bajo sirve perfectamente para detectar fiebre,
siempre que no compares sus lecturas con las de otro termómetro. De ahí sale el
reparto de tareas:

- **El simulador nomina.** Corre solo, cubre los 65 y avisa cuándo un par se
  movió lo suficiente como para mirarlo en serio. Sus lecturas se comparan
  siempre entre sí, mes contra mes.
- **El export decide.** Exportás ese par de TradingView, lo pasás por
  [`corroborar.py`](corroborar.py) y ahí sí el número está en la escala del
  informe. Recién entonces el monitor dice sacar o sumar.

Por eso los avisos vienen en dos clases, y la página muestra las dos columnas
por separado sin compararlas nunca dentro de un mismo aviso.

```bash
python monitor/corroborar.py        # mide los CSV de backtest/corroboracion/
```

---

## Cuándo avisa

Un corte seco en `t = 2` haría entrar y salir pares por el ruido de una sola
operación, así que el aviso pide **margen y memoria**:

- cruzar **1,8** hacia abajo estando en la cartera → candidato a salir
- cruzar **2,2** hacia arriba estando afuera → candidato a entrar
- y sostenerlo **dos lecturas seguidas**

Entre 1,8 y 2,2 no se decide nada. Una estrategia de 4 horas suma unas cinco a
ocho operaciones por par por mes, así que el `t` se mueve despacio y los avisos
son raros: eso es lo buscado.

La cartera vigente vive en `pool` dentro de `estado.json`. Editarla a mano es lo
correcto: el monitor avisa, la decisión es tuya.

---

## Archivos

| Archivo | Qué hace |
|---|---|
| `senales.py` | La divergencia del Pine traducida, con el RSI de Wilder y los extremos del swing |
| `simular.py` | Estado de posición y salidas replayadas: produce las operaciones |
| `actualizar.py` | La corrida mensual: mide, guarda la historia y calcula los avisos |
| `corroborar.py` | Mide desde exports de TradingView, en la escala del informe |
| `validar_senales.py` | Contrasta las señales contra los exports de TradingView |
| `validar_simulacion.py` | Contrasta las estadísticas punta a punta, a 4 horas |
| `pares.txt` | El universo monitoreado, un símbolo por línea |
| `estado.json` | Estadísticas por par, historia mensual, cartera y avisos |
| `operaciones.json` | Las operaciones generadas, para reusar sin recalcular |

Los dos JSON los escribe el script, pero solo uno se versiona. `estado.json` es
chico y guarda la historia mensual: sin él no hay con qué comparar la corrida
siguiente, así que va al repo y cada commit muestra qué cambió. `operaciones.json`
son varios megas que se reescriben enteros cada mes y se regeneran solos: es
caché, no historia, y está ignorado.

---

## Correrlo cada mes

No hay CI en este repo, así que se agenda en la máquina. En Windows, una tarea
programada mensual:

```powershell
schtasks /create /tn "RSI monitor" /sc monthly /d 1 /st 09:00 ^
  /tr "cmd /c cd /d D:\Code\RSI Divergence Strategy && python monitor\actualizar.py >> monitor\ultima-corrida.log 2>&1"
```

La primera corrida baja años de velas de 5 minutos para todos los pares y tarda
horas. Las siguientes reusan el caché en `~/.bme-cache` y solo piden el mes
nuevo.

---

## Validar después de tocar la estrategia

Si cambian los parámetros de `strategy.pine`, hay que actualizar las constantes
de `senales.py` y `simular.py`, **y volver a validar**: los exports viejos dejan
de servir como referencia en cuanto la estrategia cambia, así que hace falta
exportar de nuevo al menos unos pares y correr

```bash
python monitor/validar_senales.py --todos
python monitor/validar_simulacion.py
```

Sin ese paso, el monitor sigue reportando números con toda confianza y ninguna
base.
