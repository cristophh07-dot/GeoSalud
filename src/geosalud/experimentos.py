"""Experimentos del paper (todas las corridas usan la demanda de PRUEBA 2020-2021
para generar llamadas; las estrategias se construyen con la de ENTRENAMIENTO).

E0  Descomposición de la brecha accidente vs. emergencia médica.
E1  Estrategias de ubicación con la flota oficial (17).
E2  Ubicación vs. flota vs. tiempo de entrega en IPS.
E3  Sensibilidad (perfil horario de emergencias médicas, radio y q de MEXCLP).
E4  Validación: entrenamiento vs. prueba y casos SinRecurso por comuna (2022).
"""
import json

import numpy as np
import pandas as pd

from . import config as C
from . import estrategias as S
from .simulacion import Datos, Escenario, resumir, simular

PAR = json.load(open(C.TAB / "parametros_calibrados.json"))
BASE = dict(t_hosp=PAR["t_hosp"], alfa=PAR["alfa"], t_reg_med=PAR["t_reg_med"])
REP = 20
N0 = C.FLOTA_TAB + C.FLOTA_TAM
RADIO = 10.0


def correr(D, b, rep=REP, prioridad="accidente", **kw):
    par = BASE | kw
    filas = []
    for s in range(rep):
        ll = simular(D, Escenario(dias=30, **par), b, s, prioridad=prioridad)
        filas.append(resumir(ll) | {"rep": s})
    return pd.DataFrame(filas)


def construir(D, nombre, n, E, q):
    dem = S.demanda_entrenamiento(D, E.lam_acc, E.lam_med)
    if nombre == "Bomberos (actual aprox.)":
        return S.bomberos(D, n, dem)
    if nombre == "K-Means ponderado":
        return S.kmeans_ponderado(D, n, dem)
    if nombre == "p-mediana":
        return S.p_mediana(D, n, dem)
    if nombre == "MEXCLP":
        return S.mexclp(D, n, dem, q=q, radio=RADIO, alfa=BASE["alfa"])
    if nombre == "MEXCLP equitativo":
        return S.mexclp_equitativo(D, n, dem, q=q, radio=RADIO, alfa=BASE["alfa"])
    if nombre == "MEXCLP dinámico":
        return S.mexclp_dinamico(D, n, E.lam_acc, E.lam_med, q=q, radio=RADIO, alfa=BASE["alfa"])
    raise ValueError(nombre)


ESTRATEGIAS = ["Bomberos (actual aprox.)", "K-Means ponderado", "p-mediana", "MEXCLP",
               "MEXCLP equitativo", "MEXCLP dinámico"]


def ic(df, col):
    m, s = df[col].mean(), df[col].std(ddof=1)
    h = 1.96 * s / np.sqrt(len(df))
    return m, m - h, m + h


def e0_brecha(D):
    E = Escenario()
    b = construir(D, "Bomberos (actual aprox.)", N0, E, 0.58)
    casos = {
        "Calibrado (actual)": dict(),
        "Igual regulación": dict(t_reg_med=E.t_reg_acc),
        "Sin prioridad (FIFO)": dict(_fifo=True),
        "Igual regulación + FIFO": dict(t_reg_med=E.t_reg_acc, _fifo=True),
    }
    filas = []
    for nom, kw in casos.items():
        fifo = kw.pop("_fifo", False)
        df = correr(D, b, prioridad=None if fifo else "accidente", **kw)
        filas.append({"caso": nom, "resp_acc": df.resp_acc.mean(), "resp_med": df.resp_med.mean(),
                      "brecha": (df.resp_med - df.resp_acc).mean()})
    out = pd.DataFrame(filas)
    out.to_csv(C.TAB / "E0_brecha.csv", index=False)
    print(out.round(2).to_string(index=False))
    return out


def e1_estrategias(D, q=0.58):
    E = Escenario()
    filas, bases = [], {}
    for nom in ESTRATEGIAS:
        b = construir(D, nom, N0, E, q)
        bases[nom] = np.asarray(b).tolist()
        df = correr(D, b)
        df["estrategia"] = nom
        filas.append(df)
    df = pd.concat(filas)
    df.to_csv(C.TAB / "E1_replicas.csv", index=False)
    json.dump(bases, open(C.TAB / "E1_bases.json", "w"))
    res = df.groupby("estrategia", sort=False).agg(["mean", "std"])
    print(df.groupby("estrategia", sort=False)[["resp_media", "resp_p90", "resp_acc", "resp_med",
                                                "cob8", "cob15", "resp_rural"]].mean().round(2))
    return df


def e2_flota(D, flotas=range(13, 31), q=0.58,
             estrategias=("Bomberos (actual aprox.)", "p-mediana", "MEXCLP", "MEXCLP equitativo")):
    E = Escenario()
    filas = []
    for nom in estrategias:
        for n in flotas:
            b = construir(D, nom, n, E, q)
            df = correr(D, b, rep=10)
            m = df.mean(numeric_only=True)
            filas.append({"estrategia": nom, "flota": n, **m.to_dict(),
                          "resp_media_lo": ic(df, "resp_media")[1], "resp_media_hi": ic(df, "resp_media")[2]})
        print(nom, "listo")
    # palanca 3: tiempo de entrega en IPS, con la flota oficial
    for nom in ("Bomberos (actual aprox.)", "MEXCLP equitativo"):
        b = construir(D, nom, N0, E, q)
        for th in (BASE["t_hosp"], 120, 90, 60, 30):
            df = correr(D, b, rep=10, t_hosp=th)
            m = df.mean(numeric_only=True)
            filas.append({"estrategia": nom + " | t_hosp", "flota": N0, "t_hosp": th, **m.to_dict()})
    out = pd.DataFrame(filas)
    out.to_csv(C.TAB / "E2_flota_ubicacion.csv", index=False)
    return out


def e3_sensibilidad(D):
    E = Escenario()
    filas = []
    for perfil in ("accidentes", "plano", "diurno"):
        for nom in ("Bomberos (actual aprox.)", "MEXCLP equitativo"):
            b = construir(D, nom, N0, E, 0.58)
            df = correr(D, b, rep=10, perfil_med=perfil)
            filas.append({"parametro": "perfil_med", "valor": perfil, "estrategia": nom,
                          **df.mean(numeric_only=True).to_dict()})
    dem = S.demanda_entrenamiento(D, E.lam_acc, E.lam_med)
    for q in (0.3, 0.45, 0.58, 0.7):
        for radio in (8.0, 10.0, 12.0):
            b = S.mexclp(D, N0, dem, q=q, radio=radio, alfa=BASE["alfa"])
            df = correr(D, b, rep=10)
            filas.append({"parametro": "q_radio", "valor": f"q={q},r={radio}", "estrategia": "MEXCLP",
                          **df.mean(numeric_only=True).to_dict()})
    out = pd.DataFrame(filas)
    out.to_csv(C.TAB / "E3_sensibilidad.csv", index=False)
    return out


def e4_validacion(D):
    E = Escenario()
    filas = []
    for nom in ESTRATEGIAS:
        b = construir(D, nom, N0, E, 0.58)
        for pes in ("tr", "te"):
            df = correr(D, b, rep=10, pesos=pes)
            filas.append({"estrategia": nom, "demanda": "entrenamiento" if pes == "tr" else "prueba",
                          **df.mean(numeric_only=True).to_dict()})
    out = pd.DataFrame(filas)
    out.to_csv(C.TAB / "E4_entrenamiento_prueba.csv", index=False)

    # Sin recurso por comuna: modelo (llamadas que no encuentran ambulancia libre) vs. 2022 real
    b = construir(D, "Bomberos (actual aprox.)", N0, E, 0.58)
    sims = pd.concat([simular(D, Escenario(dias=30, **BASE), b, s) for s in range(20)])
    mod = sims.assign(sr=sims.libres == 0).groupby("comuna")["sr"].sum()
    urg = pd.read_parquet(C.PROC / "urgencias.parquet")
    real = urg[(urg.anio == 2022) & urg.sin_recurso].groupby("comuna").size()
    comp = pd.DataFrame({"modelo": mod / mod.sum(), "real_2022": real / real.sum()}).fillna(0)
    comp.to_csv(C.TAB / "E4_sin_recurso_comuna.csv")
    from scipy.stats import spearmanr, pearsonr
    rho = spearmanr(comp.modelo, comp.real_2022)
    r = pearsonr(comp.modelo, comp.real_2022)
    print(f"Sin recurso por comuna: Spearman {rho.statistic:.2f} (p={rho.pvalue:.3f}), "
          f"Pearson {r.statistic:.2f}")
    return out, comp


if __name__ == "__main__":
    import sys
    D = Datos()
    quien = sys.argv[1:] or ["e0", "e1", "e2", "e3", "e4"]
    for e in quien:
        print(f"===== {e}")
        {"e0": e0_brecha, "e1": e1_estrategias, "e2": e2_flota,
         "e3": e3_sensibilidad, "e4": e4_validacion}[e](D)
