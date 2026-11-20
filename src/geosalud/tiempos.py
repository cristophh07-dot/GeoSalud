"""Fase 3: tiempos de viaje por calle y por franja horaria.

1. Grafo dirigido a partir de la red vial de OpenStreetMap (red_vial_osm.geojson).
2. Velocidad libre por tipo de vía; de 6 a 20 h se reduce con el perfil horario
   observado en Google Traffic (corredores de Medellín, 2017-2020). Las vías locales
   se congestionan menos que las arterias (exponente 0,5).
3. Matrices de tiempo con Dijkstra (scipy) para cada franja.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from . import config as C

V_LIBRE = {  # km/h, flujo libre por clase OSM
    "motorway": 70, "trunk": 65, "primary": 50, "secondary": 45, "tertiary": 35,
    "unclassified": 30, "residential": 25, "living_street": 15,
    "motorway_link": 40, "trunk_link": 40, "primary_link": 35, "secondary_link": 30,
    "tertiary_link": 30,
}
ARTERIAS = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link",
            "primary_link", "secondary_link"}

# Franjas horarias del modelo (horas que agrupan)
FRANJAS = {
    "madrugada": list(range(0, 6)) + [22, 23],
    "manana": [6, 7, 8, 9, 10, 11],
    "tarde": [12, 13, 14, 15, 16, 19, 20, 21],
    "pico": [17, 18],
}
HORA_A_FRANJA = {h: f for f, hs in FRANJAS.items() for h in hs}

# IPS que más pacientes reciben del programa APH (campo "Hospital Remitido", 2018-2022),
# con el nombre que tienen en OpenStreetMap.
HOSPITALES_RECEPTORES = [
    "Clínica Universitaria Bolivariana", "E.S.E Hospital La María", "Clínica Las Vegas",
    "IPS Universitaria - Clínica León XIII", "Clínica Las Américas Promotora",
    "Hospital General de Medellin", "Hospital Pablo Tobón Uribe",
    "Hospital Universitario San Vicente Paul", "SOMA", "Clínica El Rosario",
    "Unidad Hospitalaria Castilla Jaime Tobón Arbeláez", "Clínica El Sagrado Corazón",
    "Unidad Hospitalaria de Buenos Aires", "Clínica Medellín", "Hospital Concejo de Medellín",
]


def factor_congestion() -> pd.Series:
    """Velocidad relativa al flujo libre por hora (1 = sin congestión)."""
    gt = pd.read_csv(C.RAW / "tiempo_viaje_gt.csv")
    v = gt.groupby("hora")["velocidad_gt_kmh"].median()
    v_libre = 1.15 * v.loc[6]          # supuesto: flujo libre 15 % sobre las 6 a. m.
    f = pd.Series(1.0, index=range(24))
    f.loc[v.index] = (v / v_libre).clip(upper=1.0)
    return f


def _clase(h):
    h = str(h).strip("[]").replace("'", "").split(",")[0].strip()
    return h


def construir_grafo():
    metro = C.RAW / "red_vial_metropolitana.geojson"
    fuente = metro if metro.exists() else C.RAW / "red_vial_osm.geojson"
    print(f"Red vial: {fuente.name}")
    r = gpd.read_file(fuente).to_crs(C.CRS_M)
    r["clase"] = r["highway"].map(_clase)
    r = r[r["clase"].isin(V_LIBRE)].copy()
    ini = np.array([g.coords[0][:2] for g in r.geometry])
    fin = np.array([g.coords[-1][:2] for g in r.geometry])
    claves = np.round(np.vstack([ini, fin]), 0)  # nodos fusionados a 1 m
    uniq, inv = np.unique(claves, axis=0, return_inverse=True)
    n = len(r)
    u, v = inv[:n], inv[n:]
    largo = r.geometry.length.values
    oneway = r["oneway"].astype(str).str.lower().isin(["true", "1", "yes"]).values
    nodos = pd.DataFrame(uniq, columns=["x", "y"])
    aristas = pd.DataFrame({"u": u, "v": v, "largo_m": largo, "clase": r["clase"].values,
                            "oneway": oneway})
    aristas = aristas[aristas.u != aristas.v]
    print(f"Grafo: {len(nodos):,} nodos, {len(aristas):,} tramos")
    return nodos, aristas


def matriz_grafo(nodos, aristas, factor, alfa=1.0):
    """Grafo con pesos en minutos para un factor de congestión dado."""
    vl = aristas["clase"].map(V_LIBRE).values
    art = aristas["clase"].isin(ARTERIAS).values
    f = np.where(art, factor, factor ** 0.5)
    vel = vl * f * alfa  # km/h
    t = aristas["largo_m"].values / 1000 / vel * 60
    u, v = aristas.u.values, aristas.v.values
    ida = ~aristas.oneway.values
    filas = np.concatenate([u, v[ida]])
    cols = np.concatenate([v, u[ida]])
    pes = np.concatenate([t, t[ida]])
    N = len(nodos)
    return csr_matrix((pes, (filas, cols)), shape=(N, N))


def componente_principal(G):
    from scipy.sparse.csgraph import connected_components
    _, lab = connected_components(G, directed=True, connection="strong")
    principal = np.bincount(lab).argmax()
    return lab == principal


def nodo_mas_cercano(nodos_xy, mask, xy):
    idx = np.where(mask)[0]
    t = cKDTree(nodos_xy[idx])
    d, i = t.query(xy)
    return idx[i], d


def construir_tiempos():
    nodos, aristas = construir_grafo()
    fac = factor_congestion()
    fac.to_csv(C.PROC / "factor_congestion.csv", header=["factor"])
    grilla = pd.read_parquet(C.PROC / "grilla.parquet")

    G0 = matriz_grafo(nodos, aristas, 1.0)
    mask = componente_principal(G0)
    xy = nodos[["x", "y"]].values
    nodo_celda, d_acceso = nodo_mas_cercano(xy, mask, grilla[["xm", "ym"]].values)
    grilla["nodo"] = nodo_celda
    grilla["d_acceso_m"] = d_acceso

    # Hospitales: destino de traslado (solo amenity=hospital)
    h = gpd.read_file(C.RAW / "hospitales_osm.geojson").to_crs(C.CRS_M)
    h = h[h["name"].isin(HOSPITALES_RECEPTORES)].copy()
    h["xm"], h["ym"] = h.geometry.x, h.geometry.y
    h = h.drop_duplicates(subset=["name"]).reset_index(drop=True)
    print(f"Hospitales receptores ubicados: {len(h)}")
    h["nodo"], _ = nodo_mas_cercano(xy, mask, h[["xm", "ym"]].values)
    h["hospital"] = np.arange(len(h))
    h.drop(columns="geometry").to_parquet(C.PROC / "hospitales.parquet", index=False)

    nodos_celda = grilla["nodo"].values
    # acceso a pie/en ambulancia desde la vía hasta el centro de la celda: 20 km/h
    acceso_min = grilla["d_acceso_m"].values / 1000 / 20 * 60

    resumen = {}
    for franja, horas in FRANJAS.items():
        f = float(fac.loc[horas].mean())
        G = matriz_grafo(nodos, aristas, f)
        # celda -> celda (candidatas a base = todas las celdas)
        uniq_n, inv = np.unique(nodos_celda, return_inverse=True)
        cols = np.concatenate([nodos_celda, h["nodo"].values])
        Dc = np.empty((len(uniq_n), len(cols)), dtype=np.float32)
        for k in range(0, len(uniq_n), 400):              # por bloques para ahorrar memoria
            Dk = dijkstra(G, directed=True, indices=uniq_n[k:k + 400])
            Dc[k:k + 400] = Dk[:, cols]
        nc = len(nodos_celda)
        T = Dc[:, :nc][inv] + acceso_min[None, :] + acceso_min[:, None]
        T = T.astype(np.float32)
        np.save(C.PROC / f"T_celda_celda_{franja}.npy", T)
        # celda -> hospital
        Th = Dc[:, nc:][inv] + acceso_min[:, None]
        np.save(C.PROC / f"T_celda_hosp_{franja}.npy", Th.astype(np.float32))
        resumen[franja] = (f, np.nanmedian(T[np.isfinite(T)]))
        print(f"{franja}: factor {f:.2f}, mediana celda-celda {resumen[franja][1]:.1f} min, "
              f"infinitos {np.isinf(T).mean():.2%}")
    grilla.to_parquet(C.PROC / "grilla.parquet", index=False)
    return resumen


if __name__ == "__main__":
    construir_tiempos()
