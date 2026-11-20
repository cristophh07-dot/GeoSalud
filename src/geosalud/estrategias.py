"""Fase 5: estrategias de ubicación de la flota.

Todas devuelven un arreglo con la celda base de cada ambulancia (n_amb,), o
(4, n_amb) en la estrategia dinámica (una configuración por franja horaria).
Las estrategias se construyen SOLO con la demanda de entrenamiento.
"""
import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

from . import config as C
from .simulacion import ORDEN_FRANJAS, Datos


def demanda_entrenamiento(D: Datos, lam_acc, lam_med, horas=None):
    """Llamadas esperadas por celda (por día) con los pesos de entrenamiento."""
    g = D.grilla
    if horas is None:
        return lam_acc * g.w_acc_tr.values + lam_med * g.w_med_tr.values
    # accidentes con su patrón espacial por hora; médicas con el perfil horario de accidentes
    a = np.load(C.PROC / "acc_celda_hora_tr.npy")[:, horas].sum(1)
    pa = D.perfil_acc[horas].sum()
    return lam_acc * pa * a / a.sum() + lam_med * pa * g.w_med_tr.values


def _celdas_candidatas(D: Datos):
    """Bases candidatas: celdas con buena conexión a la vía (< 150 m)."""
    return np.where(D.grilla["d_acceso_m"].values < 150)[0]


def bomberos(D: Datos, n_amb, dem):
    b = gpd.read_file(C.RAW / "bomberos_osm.geojson").to_crs(C.CRS_M)
    b = b[~b["name"].str.contains("Aeron", na=False)]
    xy = np.unique(np.round(np.c_[b.geometry.x, b.geometry.y], -1), axis=0)
    _, celdas = cKDTree(D.grilla[["xm", "ym"]].values).query(xy)
    celdas = np.unique(celdas)
    # reparto proporcional a la demanda más cercana en tiempo (tarde)
    T = D.T[ORDEN_FRANJAS.index("tarde")]
    asign = np.argmin(T[celdas], axis=0)
    carga = np.bincount(asign, weights=dem, minlength=len(celdas))
    return _repartir(celdas, carga, n_amb)


def _repartir(celdas, carga, n_amb):
    """Reparte n_amb proporcional a la carga, al menos 1 por base (método del mayor residuo)."""
    k = len(celdas)
    base = np.ones(k, int)
    resto = n_amb - k
    if resto < 0:
        orden = np.argsort(-carga)[:n_amb]
        return np.sort(celdas[orden])
    cuota = carga / carga.sum() * resto
    base += np.floor(cuota).astype(int)
    falta = n_amb - base.sum()
    base[np.argsort(-(cuota - np.floor(cuota)))[:falta]] += 1
    return np.repeat(celdas, base)


def kmeans_ponderado(D: Datos, n_amb, dem, k=None):
    """Método del proyecto de clase: centroides ponderados por demanda (en metros)."""
    k = k or n_amb
    m = dem > 0
    xy = D.grilla[["xm", "ym"]].values[m]
    km = KMeans(n_clusters=k, random_state=C.SEMILLA, n_init=20).fit(xy, sample_weight=dem[m])
    cand = _celdas_candidatas(D)
    _, i = cKDTree(D.grilla[["xm", "ym"]].values[cand]).query(km.cluster_centers_)
    celdas = cand[i]
    carga = np.bincount(km.labels_, weights=dem[m], minlength=k)
    return _repartir(celdas, carga, n_amb)


def p_mediana(D: Datos, n_amb, dem, franja="tarde", iter_max=20):
    """p-mediana con p = n_amb: heurística voraz + intercambio (Teitz-Bart)."""
    T = D.T[ORDEN_FRANJAS.index(franja)]
    cand = _celdas_candidatas(D)
    m = dem > 0
    Tc = T[np.ix_(cand, np.where(m)[0])]
    w = dem[m]
    sel = []
    mejor = np.full(Tc.shape[1], np.inf)
    for _ in range(n_amb):
        costo = (np.minimum(Tc, mejor) * w).sum(1)
        j = int(np.argmin(costo))
        sel.append(j)
        mejor = np.minimum(mejor, Tc[j])
    sel = np.array(sel)
    for _ in range(iter_max):
        mejora = False
        for pos in range(len(sel)):
            otros = np.delete(sel, pos)
            base_otros = Tc[otros].min(0)
            costo = (np.minimum(Tc, base_otros) * w).sum(1)
            j = int(np.argmin(costo))
            actual = (np.minimum(Tc[sel[pos]], base_otros) * w).sum()
            if costo[j] < actual - 1e-6:
                sel[pos] = j
                mejora = True
        if not mejora:
            break
    return np.sort(cand[sel])


def mexclp(D: Datos, n_amb, dem, q=0.3, radio=10.0, franja="tarde", alfa=1.0, fijas=()):
    """MEXCLP (Daskin, 1983), heurística voraz clásica.
    Maximiza sum_i h_i sum_k (1-q) q^(k-1) y_ik con cobertura = viaje <= radio min.
    Se permite más de una ambulancia por base. `fijas`: celdas que se imponen primero."""
    T = D.T[ORDEN_FRANJAS.index(franja)] / alfa
    cand = _celdas_candidatas(D)
    m = dem > 0
    cub = (T[np.ix_(cand, np.where(m)[0])] <= radio)
    w = dem[m]
    k_i = np.zeros(cub.shape[1])          # ambulancias que ya cubren cada celda
    sel = []
    for c in fijas:
        j = int(np.where(cand == c)[0][0]) if c in cand else int(np.argmin(np.abs(cand - c)))
        sel.append(cand[j])
        k_i += cub[j]
    for _ in range(n_amb - len(sel)):
        ganancia = (cub * (w * (1 - q) * q ** k_i)).sum(1)
        j = int(np.argmax(ganancia))
        sel.append(cand[j])
        k_i += cub[j]
    return np.sort(np.array(sel))


def mexclp_equitativo(D: Datos, n_amb, dem, q=0.3, radio=10.0, alfa=1.0, umbral=0.01):
    """MEXCLP con una ambulancia garantizada en cada corregimiento que concentra al menos
    `umbral` de la demanda (la celda candidata que minimiza su tiempo medio ponderado)."""
    T = D.T[ORDEN_FRANJAS.index("tarde")] / alfa
    cand = _celdas_candidatas(D)
    com = D.grilla["comuna"].values
    fijas = []
    for c in (50, 60, 70, 80, 90):
        mc = com == c
        if dem[mc].sum() / dem.sum() < umbral:
            continue
        cc = cand[com[cand] == c]
        costo = (T[np.ix_(cc, np.where(mc)[0])] * dem[mc]).sum(1)
        fijas.append(cc[int(np.argmin(costo))])
    return mexclp(D, n_amb, dem, q=q, radio=radio, alfa=alfa, fijas=fijas)


def mexclp_dinamico(D: Datos, n_amb, lam_acc, lam_med, q=0.3, radio=10.0, alfa=1.0):
    from .tiempos import FRANJAS
    filas = []
    for f in ORDEN_FRANJAS:
        dem = demanda_entrenamiento(D, lam_acc, lam_med, horas=FRANJAS[f])
        filas.append(mexclp(D, n_amb, dem, q=q, radio=radio, franja=f, alfa=alfa))
    # empareja ambulancias entre franjas para minimizar desplazamientos
    from scipy.optimize import linear_sum_assignment
    out = [filas[0]]
    for f in range(1, len(filas)):
        Tm = D.T[f][np.ix_(out[-1], filas[f])]
        r, c = linear_sum_assignment(Tm)
        out.append(filas[f][c[np.argsort(r)]])
    return np.vstack(out)
