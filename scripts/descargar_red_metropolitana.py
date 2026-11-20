"""Descarga la red vial (para carros) de Medellín y sus vecinos del Valle de Aburrá.

Por qué: la red recortada al límite de Medellín deja a San Antonio de Prado, Altavista
y otros corregimientos sin sus conexiones reales, que pasan por Itagüí, La Estrella
o Bello, y los tiempos de viaje salen inflados.

Uso (desde la raíz del repo, con internet):
    pip install osmnx
    python scripts/descargar_red_metropolitana.py
Salida: data/raw/red_vial_metropolitana.geojson  (~40-60 MB, tarda unos minutos)
"""
from pathlib import Path

import osmnx as ox

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "raw" / "red_vial_metropolitana.geojson"

# Caja que cubre Medellín, Bello, Itagüí, Envigado, Sabaneta y La Estrella
NORTE, SUR, ESTE, OESTE = 6.40, 6.10, -75.45, -75.72

print("Descargando red vial... (puede tardar varios minutos)")
G = ox.graph_from_bbox(bbox=(OESTE, SUR, ESTE, NORTE), network_type="drive", simplify=True)
_, vias = ox.graph_to_gdfs(G)
vias = vias.reset_index(drop=True)
vias = vias[["osmid", "name", "highway", "length", "oneway", "geometry"]].copy()
for c in ("osmid", "name", "highway"):
    vias[c] = vias[c].astype(str)
vias.to_file(SALIDA, driver="GeoJSON")
print(f"Listo: {len(vias):,} tramos en {SALIDA}")
