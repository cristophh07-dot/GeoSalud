"""Corre todo el pipeline de punta a punta:  python scripts/run_all.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geosalud import calibracion, demanda, experimentos, figuras, limpieza, tiempos  # noqa: E402
from geosalud.simulacion import Datos  # noqa: E402

pasos = [
    ("1. Limpieza", lambda: (limpieza.limpiar_accidentes(), limpieza.limpiar_urgencias())),
    ("2. Grilla y demanda", demanda.construir_demanda),
    ("3. Tiempos de viaje", tiempos.construir_tiempos),
    ("4. Calibración", calibracion.calibrar),
]
for nombre, f in pasos:
    t = time.time()
    print(f"\n=== {nombre}")
    f()
    print(f"({time.time() - t:.0f} s)")

import importlib  # noqa: E402
importlib.reload(experimentos)   # relee los parámetros recién calibrados
D = Datos()
for e in (experimentos.e0_brecha, experimentos.e1_estrategias, experimentos.e2_flota,
          experimentos.e3_sensibilidad, experimentos.e4_validacion):
    print(f"\n=== {e.__name__}")
    e(D)
importlib.reload(figuras)
print("\n=== Figuras")
figuras.fig_brecha(); figuras.fig_flota(); figuras.fig_palancas(); figuras.fig_validacion()
figuras.fig_equidad_y_mapa(D)
print("\nListo. Resultados en results/")
