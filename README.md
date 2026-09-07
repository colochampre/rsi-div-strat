# RSI Divergence Strategy

Estrategia de trading en Pine Script que opera divergencias entre el precio y el
RSI, más el instrumental para validarla: exports de backtest de TradingView y
scripts de análisis que responden si el resultado se sostiene fuera de los datos
donde se ajustó.

El repositorio tiene dos mitades. `strategy.pine` es lo que se ejecuta en el
gráfico; `analysis/` es lo que decide si eso merece confianza.

## Estructura del repositorio

| Ruta | Qué contiene |
|---|---|
| `strategy.pine` | La estrategia completa: señales, entradas, salidas y gestión de riesgo. |
| `indicators/` | Indicadores auxiliares de solo visualización (`rsi-div.pine`, `sar.pine`). No participan de las órdenes. |
| `backtest/` | Exports de la lista de operaciones de TradingView, más `configs.csv` con el resumen de corridas. Los exports de la validación 4h están versionados para que los scripts de `analysis/` sean reproducibles; corridas nuevas se regeneran desde TradingView. |
| `analysis/` | Scripts de Python que validan esos exports. Ver [`analysis/README.md`](analysis/README.md). |

## Cómo está armada la estrategia

El archivo sigue un pipeline lineal, y cada bloque está separado por un
encabezado con ese mismo orden:

```
RSI → Divergencias → Señales → Entradas → Salidas → Riesgo → Plots → Alertas
```

### 1. RSI y detección de swings

Se calcula el RSI y se rastrean, dentro de una ventana móvil, el máximo y el
mínimo vigentes tanto de precio como de RSI. Estos extremos son la referencia
contra la que se mide cualquier divergencia: no hay pivotes confirmados con
retardo, el extremo se actualiza vela a vela.

### 2. Motor de divergencias

Dos condiciones simétricas:

- **Bajista** — el precio marca un máximo más alto que el anterior mientras el
  RSI no acompaña, y el RSI empieza a girar a la baja.
- **Alcista** — el precio marca un mínimo más bajo que el anterior mientras el
  RSI no acompaña, y el RSI empieza a girar al alza.

Opcionalmente la divergencia solo se considera válida si el extremo del RSI
ocurrió dentro de la zona de sobrecompra o sobreventa. Ese filtro es lo que
distingue una divergencia con contexto de una casual en mitad del rango.

### 3. Señales y entradas

Cada divergencia válida se convierte en señal según el sentido habilitado. Long
y short se pueden activar por separado. Una señal opuesta con posición abierta
invierte el lado en vez de acumular: la estrategia está siempre en un único
sentido o fuera.

### 4. Salidas

Hay tres mecanismos de salida y conviven:

| Mecanismo | Cuándo actúa |
|---|---|
| Divergencia opuesta | Cierra la posición cuando aparece la señal contraria. |
| Take profit / stop loss fijos | Niveles calculados como porcentaje sobre el precio promedio de entrada. |
| Trailing stop | Se arma recién cuando el precio alcanza un nivel de activación, y después sigue al extremo a favor a una distancia fija. Nunca retrocede. |

El cierre por divergencia opuesta es una orden aparte. Take profit, stop loss y
trailing viajan juntos en una única orden de salida por lado, reenviada en cada
vela al mismo identificador: Pine reemplaza la orden existente en lugar de
duplicarla. Sale el nivel que se toque primero.

### 5. Visualización del riesgo

Los niveles de stop se dibujan sobre el gráfico de precio y el área entre el
precio y el stop vigente se sombrea. Mientras el trailing no está armado, el
stop real es el fijo; una vez armado, el fijo deja de serlo y el área cambia de
color en vez de superponerse. Lo que se ve en pantalla es el mismo valor que
recibe la orden, no una reconstrucción aparte.

### 6. Alertas

Se exponen condiciones separadas para divergencias detectadas y para señales de
entrada efectivas, que no son lo mismo: una divergencia puede detectarse con su
lado deshabilitado.

## Cómo usarlo

1. Cargar `strategy.pine` en el editor de Pine de TradingView y agregarlo al
   gráfico.
2. Ajustar los parámetros desde el panel de inputs, agrupados por bloque (RSI,
   entradas, salidas).
3. Exportar la lista de operaciones a `backtest/` respetando la nomenclatura que
   documenta [`analysis/README.md`](analysis/README.md).
4. Correr los scripts de `analysis/` para validar el resultado.

## Estado de la validación

Los hallazgos de la última validación, con la configuración congelada y las
limitaciones conocidas, están en
[`analysis/HALLAZGOS.md`](analysis/HALLAZGOS.md).
