"""Rutas y parámetros globales del proyecto GeoSalud.

Todas las rutas son relativas a la raíz del repositorio, así el pipeline
corre igual en cualquier computador.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RAW = RAIZ / "data" / "raw"
PROC = RAIZ / "data" / "processed"
FIG = RAIZ / "results" / "figures"
TAB = RAIZ / "results" / "tables"

for _d in (PROC, FIG, TAB):
    _d.mkdir(parents=True, exist_ok=True)

# Sistemas de referencia: WGS84 para guardar, MAGNA-SIRGAS / Colombia Bogotá
# (EPSG:3116, metros) para medir distancias y construir la grilla.
CRS_GEO = "EPSG:4326"
CRS_M = "EPSG:3116"

# Caja de Medellín (para descartar coordenadas mal digitadas)
LAT_MIN, LAT_MAX = 6.10, 6.40
LON_MIN, LON_MAX = -75.72, -75.45

TAM_CELDA_M = 300

# Partición temporal: se construye con 2014-2019 y se evalúa con 2020-2021
ANIOS_ENTRENA = range(2014, 2020)
ANIOS_PRUEBA = range(2020, 2022)

# Jornadas (definición del proyecto de clase, horas inclusivas)
JORNADA_DIA = range(6, 22)   # 06:00-21:59
SEMILLA = 42

# Flota oficial (respuesta a derecho de petición, radicado 202630266483, 1-jun-2026)
FLOTA_TAB = 15
FLOTA_TAM = 2
