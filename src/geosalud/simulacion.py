"""Fase 4: simulación de eventos discretos del programa APH de Medellín.

Ciclo de cada llamada:
  llamada -> regulación (t_reg) -> espera de ambulancia libre (cola FIFO)
  -> viaje base->escena -> atención en escena -> [traslado a la IPS + entrega]
  -> regreso a su base.
Tiempo de respuesta = desde la llamada hasta la llegada a la escena
  (regulación + espera + viaje), la definición más cercana al tablero de MEData.

La asignación elige la ambulancia que llega primero a la escena, considerando las
que están ocupadas (ocurre en el orden de llegada de las llamadas).
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from .tiempos import FRANJAS, HORA_A_FRANJA

ORDEN_FRANJAS = list(FRANJAS)
F_IDX = np.array([ORDEN_FRANJAS.index(HORA_A_FRANJA[h]) for h in range(24)])


@dataclass
class Escenario:
    lam_acc: float = 47.0          # llamadas con despacho por día (2026: 83,6/día, 56 % accidentes)
    lam_med: float = 37.0
    t_reg_acc: float = 3.0         # min de regulación telefónica antes del despacho
    t_reg_med: float = 3.0
    alfa: float = 1.0              # velocidad de la ambulancia relativa al tráfico
    escena: float = 15.0           # min promedio en escena
    p_traslado: float = 0.73       # proporción trasladada a una IPS (registro APH 2018-2022)
    t_hosp: float = 30.0           # min de entrega del paciente en la IPS
    dias: int = 30
    calentamiento: int = 2
    pesos: str = "te"              # "tr" (entrenamiento) o "te" (prueba) para generar llamadas
    perfil_med: str = "accidentes"  # perfil horario de las emergencias médicas
    extra: dict = field(default_factory=dict)


class Datos:
    """Carga una sola vez las matrices de tiempos y la demanda."""

    def __init__(self):
        P = C.PROC
        self.grilla = pd.read_parquet(P / "grilla.parquet")
        self.T = np.stack([np.load(P / f"T_celda_celda_{f}.npy") for f in ORDEN_FRANJAS])
        self.Th = np.stack([np.load(P / f"T_celda_hosp_{f}.npy") for f in ORDEN_FRANJAS])
        self.perfil_acc = np.load(P / "perfil_horario_accidentes.npy")
        h = pd.read_parquet(P / "hospitales.parquet")
        from scipy.spatial import cKDTree
        t = cKDTree(self.grilla[["xm", "ym"]].values)
        _, self.celda_hosp = t.query(h[["xm", "ym"]].values)
        self.comuna = self.grilla["comuna"].values

    def perfil(self, cual):
        if cual == "accidentes":
            return self.perfil_acc
        if cual == "plano":
            return np.full(24, 1 / 24)
        if cual == "diurno":   # emergencias médicas concentradas 8-20 h
            p = np.where((np.arange(24) >= 8) & (np.arange(24) <= 20), 2.0, 1.0)
            return p / p.sum()
        raise ValueError(cual)


def generar_llamadas(D: Datos, E: Escenario, rng):
    total = E.dias + E.calentamiento
    filas = []
    for tipo, lam, perfil in (("accidente", E.lam_acc, D.perfil_acc),
                              ("medica", E.lam_med, D.perfil(E.perfil_med))):
        n = rng.poisson(lam * total)
        dia = rng.integers(0, total, n)
        hora = rng.choice(24, n, p=perfil)
        minuto = rng.uniform(0, 60, n)
        w = D.grilla[f"w_{'acc' if tipo == 'accidente' else 'med'}_{E.pesos}"].values
        celda = rng.choice(len(w), n, p=w / w.sum())
        filas.append(pd.DataFrame({"t": dia * 1440 + hora * 60 + minuto, "tipo": tipo,
                                   "celda": celda, "hora": hora}))
    ll = pd.concat(filas).sort_values("t").reset_index(drop=True)
    return ll


def _lognormal(rng, media, cv=0.5):
    s2 = np.log(1 + cv ** 2)
    return rng.lognormal(np.log(media) - s2 / 2, np.sqrt(s2))


def simular(D: Datos, E: Escenario, bases, semilla=0, prioridad="accidente"):
    """Simulación por eventos con cola de prioridad.

    bases: (n_amb,) celda base de cada ambulancia, o (4, n_amb) una por franja (dinámica).
    prioridad: "accidente" (los accidentes en vía pública pasan primero en la cola)
               o None (cola FIFO pura).
    Una llamada que encuentra todas las ambulancias ocupadas espera en cola; cuando una
    ambulancia regresa a su base atiende la llamada de mayor prioridad más antigua.
    """
    import heapq
    rng = np.random.default_rng(semilla)
    bases = np.asarray(bases)
    dinamica = bases.ndim == 2
    n = bases.shape[-1]
    base_act = (bases[0] if dinamica else bases).copy()
    ocupada = np.zeros(n, bool)
    ll = generar_llamadas(D, E, rng)
    T, Th = D.T, D.Th
    N = len(ll)
    t_arr = ll.t.values
    tipo = ll.tipo.values
    celda = ll.celda.values
    res = np.full((N, 5), np.nan)   # respuesta, espera, viaje, ambulancia, libres_al_llamar

    ev = []   # (tiempo, orden, clase, dato); clase 0 = ambulancia libre, 1 = llamada lista
    for k in range(N):
        t_reg = E.t_reg_acc if tipo[k] == "accidente" else E.t_reg_med
        heapq.heappush(ev, (t_arr[k] + t_reg, 1, 1, k))
    if dinamica:
        total = (E.dias + E.calentamiento) * 1440
        cambios = [h * 60 for h in range(0, int(total // 60))
                   if F_IDX[h % 24] != F_IDX[(h - 1) % 24]]
        for tc in cambios:
            heapq.heappush(ev, (tc, 0, 2, -1))
    cola = []   # (prioridad, t_llamada, k)
    contador = 2

    def franja(t):
        return F_IDX[int(t // 60) % 24]

    def despachar(a, k, t):
        nonlocal contador
        fr = franja(t)
        viaje = T[fr, base_act[a], celda[k]] / E.alfa
        llega = t + viaje
        listo = t_arr[k] + (E.t_reg_acc if tipo[k] == "accidente" else E.t_reg_med)
        res[k, 0] = llega - t_arr[k]
        res[k, 1] = t - listo
        res[k, 2] = viaje
        res[k, 3] = a
        fin = llega + _lognormal(rng, E.escena)
        if rng.random() < E.p_traslado:
            th = Th[fr, celda[k]] / E.alfa
            h = int(np.argmin(th))
            en_ips = fin + th[h] + _lognormal(rng, E.t_hosp, 0.6)
            vuelta = en_ips + T[fr, D.celda_hosp[h], base_act[a]] / E.alfa
        else:
            vuelta = fin + T[fr, celda[k], base_act[a]] / E.alfa
        ocupada[a] = True
        contador += 1
        heapq.heappush(ev, (vuelta, contador, 0, a))

    while ev:
        t, _, clase, dato = heapq.heappop(ev)
        if clase == 1:                          # llamada lista para despacho
            k = dato
            libres = np.where(~ocupada)[0]
            res[k, 4] = len(libres)
            if len(libres):
                fr = franja(t)
                a = libres[np.argmin(T[fr, base_act[libres], celda[k]])]
                despachar(a, k, t)
            else:
                pr = 0 if (prioridad == "accidente" and tipo[k] == "accidente") else 1
                heapq.heappush(cola, (pr, t_arr[k], k))
        elif clase == 0:                        # ambulancia de vuelta en su base
            a = dato
            ocupada[a] = False
            if dinamica:
                nueva = bases[franja(t)][a]
                if nueva != base_act[a]:
                    fr = franja(t)
                    ocupada[a] = True
                    contador += 1
                    heapq.heappush(ev, (t + T[fr, base_act[a], nueva] / E.alfa, contador, 0, a))
                    base_act[a] = nueva
                    continue
            if cola:
                _, _, k = heapq.heappop(cola)
                despachar(a, k, t)
        else:                                   # cambio de franja: reubicar las libres
            fr = franja(t)
            for a in np.where(~ocupada)[0]:
                nueva = bases[fr][a]
                if nueva != base_act[a]:
                    ocupada[a] = True
                    contador += 1
                    heapq.heappush(ev, (t + T[fr, base_act[a], nueva] / E.alfa, contador, 0, a))
                    base_act[a] = nueva

    ll[["respuesta", "espera", "viaje", "ambulancia", "libres"]] = res
    ll["comuna"] = D.comuna[ll.celda.values]
    ll = ll[ll.t >= E.calentamiento * 1440].dropna(subset=["respuesta"]).reset_index(drop=True)
    ll["n_amb"] = n
    return ll


def resumir(ll: pd.DataFrame) -> dict:
    r = ll["respuesta"]
    out = {
        "resp_media": r.mean(), "resp_p90": r.quantile(0.9),
        "resp_acc": r[ll.tipo == "accidente"].mean(),
        "resp_med": r[ll.tipo == "medica"].mean(),
        "cob8": (r <= 8).mean(), "cob15": (r <= 15).mean(),
        "espera_media": ll["espera"].mean(), "p_espera": (ll["espera"] > 0.01).mean(),
        "viaje_medio": ll["viaje"].mean(),
        "p_sin_recurso": (ll["libres"] == 0).mean(),
        "ocupacion": 1 - ll["libres"].mean() / ll["n_amb"].iloc[0],
    }
    urb = ll.comuna <= 16
    out["resp_urbana"] = r[urb].mean()
    out["resp_rural"] = r[~urb].mean() if (~urb).any() else np.nan
    return out
