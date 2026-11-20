"""Fase 2: grilla de 300 m y demanda esperada por celda y hora.

Demanda = llamadas que requieren despacho de ambulancia del programa APH.
- Accidentes: distribución espacio-horaria tomada de los incidentes georreferenciados
  de la Secretaría de Movilidad (MEData), escalada al volumen que atiende el APH.
- Emergencias médicas: el registro APH solo trae barrio. Cada caso se reparte de forma
  uniforme entre las celdas de su barrio. La geometría de cada barrio se aproxima con
  las celdas cuyos accidentes registran ese barrio (supuesto declarado en el paper).
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from . import config as C
from .limpieza import codigo_comuna


def construir_grilla() -> gpd.GeoDataFrame:
    com = gpd.read_file(C.RAW / "comunas_osm.geojson")
    com = com[~com["name"].str.contains("Perímetro", na=False)].copy()
    com["comuna"] = com["name"].map(codigo_comuna)
    com = com.to_crs(C.CRS_M)[["comuna", "name", "geometry"]]
    com.to_file(C.PROC / "comunas.geojson", driver="GeoJSON")

    x0, y0, x1, y1 = com.total_bounds
    s = C.TAM_CELDA_M
    xs, ys = np.arange(x0, x1, s), np.arange(y0, y1, s)
    celdas = [box(x, y, x + s, y + s) for x in xs for y in ys]
    g = gpd.GeoDataFrame(geometry=celdas, crs=C.CRS_M)
    g["xm"], g["ym"] = g.centroid.x, g.centroid.y
    pts = gpd.GeoDataFrame(g[["xm", "ym"]], geometry=gpd.points_from_xy(g["xm"], g["ym"]), crs=C.CRS_M)
    pts = gpd.sjoin(pts, com, how="inner", predicate="within")
    g = g.loc[pts.index].copy()
    g["comuna"] = pts["comuna"].values
    g = g.reset_index(drop=True)
    g["celda"] = np.arange(len(g))
    ll = gpd.GeoSeries(gpd.points_from_xy(g["xm"], g["ym"]), crs=C.CRS_M).to_crs(C.CRS_GEO)
    g["lon"], g["lat"] = ll.x.values, ll.y.values
    print(f"Grilla: {len(g):,} celdas de {s} m")
    return g


def _asignar_celda(df, lon, lat, grilla):
    p = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs=C.CRS_GEO).to_crs(C.CRS_M)
    j = gpd.sjoin(p, grilla[["celda", "geometry"]], how="left", predicate="within")
    return j["celda"]


def construir_demanda():
    grilla = construir_grilla()
    acc = pd.read_parquet(C.PROC / "accidentes.parquet")
    acc["celda"] = _asignar_celda(acc, "lon", "lat", grilla).values
    acc = acc.dropna(subset=["celda"])
    acc["celda"] = acc["celda"].astype(int)
    acc.to_parquet(C.PROC / "accidentes_celda.parquet", index=False)

    # Barrio de cada celda: el más frecuente entre sus accidentes; si no tiene, el de la celda más cercana.
    moda = acc.groupby("celda")["barrio_n"].agg(lambda s: s.mode().iloc[0] if s.notna().any() else None)
    grilla["barrio_n"] = grilla["celda"].map(moda)
    con = grilla[grilla.barrio_n.notna()]
    from scipy.spatial import cKDTree
    t = cKDTree(con[["xm", "ym"]].values)
    falt = grilla.barrio_n.isna()
    _, i = t.query(grilla.loc[falt, ["xm", "ym"]].values)
    grilla.loc[falt, "barrio_n"] = con["barrio_n"].values[i]

    # --- Accidentes: conteo por celda y hora, entrenamiento y prueba
    def conteo(df):
        m = df.pivot_table(index="celda", columns="hora", values="Radicado", aggfunc="count", fill_value=0)
        return m.reindex(index=grilla.celda, columns=range(24), fill_value=0)

    a_tr = conteo(acc[acc.anio.isin(C.ANIOS_ENTRENA)])
    a_te = conteo(acc[acc.anio.isin(C.ANIOS_PRUEBA)])

    # --- Emergencias médicas: por barrio (casos con despacho)
    urg = pd.read_parquet(C.PROC / "urgencias.parquet")
    med = urg[(urg.tipo == "medica") & urg.despacho]
    celdas_barrio = grilla.groupby("barrio_n")["celda"].apply(list)
    celdas_comuna = grilla.groupby("comuna")["celda"].apply(list)

    def reparto(df):
        v = np.zeros(len(grilla))
        sin = 0
        for (b, c), n in df.groupby(["barrio_n", "comuna"], dropna=False).size().items():
            if b in celdas_barrio.index:
                cs = celdas_barrio[b]
            elif c in celdas_comuna.index:
                cs = celdas_comuna[c]
            else:
                sin += n
                continue
            v[cs] += n / len(cs)
        return v, sin

    m_tr, s1 = reparto(med[med.anio.isin([2018, 2019])])
    m_te, s2 = reparto(med[med.anio.isin([2020, 2021])])
    print(f"Emergencias médicas sin barrio ni comuna asignable: {s1 + s2:,}")

    # Tabla de pesos espaciales por celda (proporciones que suman 1)
    grilla["w_acc_tr"] = a_tr.sum(1).values / a_tr.values.sum()
    grilla["w_acc_te"] = a_te.sum(1).values / a_te.values.sum()
    grilla["w_med_tr"] = m_tr / m_tr.sum()
    grilla["w_med_te"] = m_te / m_te.sum()

    # Perfil horario de accidentes (entrenamiento), por celda suavizado hacia el perfil de su comuna
    perfil_ciudad = a_tr.values.sum(0) / a_tr.values.sum()
    np.save(C.PROC / "perfil_horario_accidentes.npy", perfil_ciudad)
    np.save(C.PROC / "acc_celda_hora_tr.npy", a_tr.values)
    np.save(C.PROC / "acc_celda_hora_te.npy", a_te.values)

    grilla.to_file(C.PROC / "grilla.geojson", driver="GeoJSON")
    grilla.drop(columns="geometry").to_parquet(C.PROC / "grilla.parquet", index=False)
    print("Demanda guardada")
    return grilla


if __name__ == "__main__":
    construir_demanda()
