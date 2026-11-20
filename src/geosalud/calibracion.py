"""Calibración del gemelo digital contra datos observados.

Objetivos (2026, tablero MEData de la Secretaría de Salud, y registro APH 2022):
- tiempo medio de llegada a accidentes de tránsito: 13,7 min (promedio ene-sep 2026)
- tiempo medio de llegada a emergencias médicas: 20,4 min (promedio ene-sep 2026)
- proporción de despachos sin recurso disponible: 6,7 % (casos "SinRecurso" / despachos, 2022)

Parámetros calibrados: t_hosp (min de entrega en la IPS), alfa (velocidad relativa)
y t_reg_med (regulación de emergencias médicas). La flota inicial se ubica en las
estaciones de bomberos (aproximación a la operación actual).
"""
import itertools
import json

import numpy as np
import pandas as pd

from . import config as C
from . import estrategias as S
from .simulacion import Datos, Escenario, resumir, simular

OBJ = {"resp_acc": 13.7, "resp_med": 20.4, "p_sin_recurso": 0.067}
ESCALA = {"resp_acc": 1.0, "resp_med": 1.0, "p_sin_recurso": 0.01}


def evaluar(D, b, rep=5, **kw):
    rs = [resumir(simular(D, Escenario(dias=60, **kw), b, s)) for s in range(rep)]
    return {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}


def calibrar():
    D = Datos()
    E0 = Escenario()
    dem = S.demanda_entrenamiento(D, E0.lam_acc, E0.lam_med)
    b = S.bomberos(D, C.FLOTA_TAB + C.FLOTA_TAM, dem)
    filas = []
    for th, al, trm in itertools.product([135, 140, 145, 150, 155], [0.9, 0.95, 1.0, 1.05],
                                         [3, 4, 5, 6, 7]):
        m = evaluar(D, b, rep=4, t_hosp=th, alfa=al, t_reg_med=trm)
        err = sum(((m[k] - v) / ESCALA[k]) ** 2 for k, v in OBJ.items())
        filas.append({"t_hosp": th, "alfa": al, "t_reg_med": trm, "error": err, **m})
    df = pd.DataFrame(filas).sort_values("error")
    df.to_csv(C.TAB / "calibracion_grilla.csv", index=False)
    mejor = df.iloc[0]
    par = {k: float(mejor[k]) for k in ("t_hosp", "alfa", "t_reg_med")}
    # verificación con más réplicas
    v = evaluar(D, b, rep=20, **par)
    par["verificacion"] = {k: round(v[k], 3) for k in OBJ} | {"ocupacion": round(v["ocupacion"], 3)}
    par["objetivos"] = OBJ
    json.dump(par, open(C.TAB / "parametros_calibrados.json", "w"), indent=2)
    print(json.dumps(par, indent=2))
    return par


if __name__ == "__main__":
    calibrar()
