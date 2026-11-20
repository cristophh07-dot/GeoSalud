# Datos

Los archivos de datos no se suben al repositorio por su tamaño. Para reproducir el
pipeline, copia estos archivos en `data/raw/` con estos nombres:

| Archivo en `data/raw/` | Fuente | Contenido |
| --- | --- | --- |
| `accidentes_victimas_medata.csv` | MEData, Secretaría de Movilidad (incidentes viales con víctimas 2014-2021) | Una fila por víctima, con coordenadas, fecha y hora |
| `urgencias_aph.csv` | Datos Abiertos, "Atención de situaciones de urgencias" (programa APH, 2018-2022) | Casos del programa APH: tipo, estado, barrio, comuna, IPS receptora |
| `comunas_osm.geojson` | OpenStreetMap (osmnx) | Comunas y corregimientos de Medellín |
| `hospitales_osm.geojson` | OpenStreetMap | Hospitales y clínicas |
| `bomberos_osm.geojson` | OpenStreetMap | Estaciones de bomberos |
| `red_vial_osm.geojson` | OpenStreetMap | Red vial de Medellín (recortada al municipio) |
| `red_vial_metropolitana.geojson` | OpenStreetMap, `scripts/descargar_red_metropolitana.py` | Red vial del Valle de Aburrá (recomendada) |
| `tiempo_viaje_gt.csv` | Google Traffic por corredor 2017-2020 (proyecto *Segundos contra vidas*) | Velocidad por corredor y hora |
| `poblacion_comunas.csv` | DAP, proyecciones de población por comuna | Población 2016-2030 |

`data/processed/` se genera con `python scripts/run_all.py`.

Fuentes institucionales usadas para calibrar (no son archivos):

- Tablero Power BI "Atención prehospitalaria en emergencias médicas y accidentes",
  Secretaría de Salud de Medellín (UGIC), publicado en MEData; consultado el 20-nov-2026.
- Respuesta a derecho de petición, radicado 202630266483 (1-jun-2026): 15 ambulancias TAB
  y 2 TAM operadas por la ESE Metrosalud.
