# Hallazgos de validación — 2026-08-14

Resumen de la validación de la estrategia sobre exports 4h. Los números se
reproducen corriendo los scripts de esta carpeta contra `../backtest/`.

## Configuración validada

| Parámetro | Valor |
|---|---|
| Timeframe | 4h |
| Trailing activación | 1.0% |
| Trailing offset | 0.5% |
| Stop Loss fijo | 1.90% |
| Take Profit | 3.10% |
| Comisión | 0.05% por lado |

## Evidencia a favor

**Out-of-sample.** Parámetros ajustados sobre SOL; congelados y aplicados a ETH,
AAVE, ALICE y CHR. Los 4 rentables, PF entre 1.58 y 2.39. El PF mediano
out-of-sample (2.05) supera al in-sample (1.67).

**Estabilidad por régimen.** 25 símbolo-años entre 2022 y 2026, ninguno con
PF < 1. El resultado atraviesa bear, recuperación y bull.

**Elección del offset.** Comparación pareada 0.5% vs 1.0% sobre los mismos
símbolos: gana 0.5% en 5/5 símbolos, 5/5 con slippage y 25/25 símbolo-años. El
drawdown mejora o queda igual en todos.

**Mecanismo.** El offset es cuánto se devuelve desde el máximo alcanzado, así que
reducirlo captura más de cualquier movimiento (promedio por salida de trailing:
0.75% → 1.20%). El costo son runners cortados antes del take profit (salidas por
TP caen ~20%). El primer efecto domina.

**Piso.** El peor resultado posible de una salida por trailing es
`activación − offset − comisión` = +0.4%. Se cumple exacto en los 5 símbolos.
Cero salidas por trailing en pérdida sobre 1007 operaciones.

**Robustez sin bar magnifier.** Forzando toda operación ambigua a stop loss
completo y cobrando 0.05% de slippage en cada salida por trailing, los 5 símbolos
siguen positivos. Peor caso: ETH con PF 1.51. El resultado no depende de las
suposiciones del emulador sobre el recorrido intra-vela.

## Limitaciones conocidas

**Correlación entre símbolos: 0.71.** Los 5 son alts de cripto en la misma
ventana temporal. No son 5 pruebas independientes; el número efectivo está más
cerca de 2. Una validación más dura requiere otro timeframe u otra clase de
activo.

**Slippage no modelado en el simulador.** La dispersión del fill tiene desvío de
0.015% en todas las corridas: el emulador llena siempre en
`extremo − offset` exacto, sin excepción. Las cotas de los scripts lo compensan
manualmente, pero conviene cargar slippage en las propiedades de la estrategia.

**Realizabilidad del fill.** No es medible con estos datos. Un stop 0.5% por
debajo del máximo es un retroceso que el mercado efectivamente recorre en una
vela de ~2.4% de rango. Uno de 0.2% queda dentro del ruido y del spread. Este es
el motivo para no seguir reduciendo el offset, y es independiente de la
ambigüedad de orden (que no empeora al apretar).

## Decisión

Configuración congelada. Seguir optimizando desde acá agrega sobreajuste sin
mejora distinguible del ruido. El siguiente paso es forward testing en papel, no
otro backtest.
