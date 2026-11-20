"""Fase 1: limpieza de las fuentes crudas.

Salidas en data/processed/:
- accidentes.parquet : un registro por INCIDENTE (no por víctima), con coordenadas.
- urgencias.parquet  : casos del programa APH (accidentes + emergencias médicas).
"""
import re
import unicodedata

import numpy as np
import pandas as pd

from . import config as C

CORREGIMIENTOS = {
    "palmitas": 50, "san sebastian de palmitas": 50,
    "san cristobal": 60, "altavista": 70,
    "san antonio de prado": 80, "santa elena": 90,
}


def _sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def codigo_comuna(nombre) -> float:
    """Convierte cualquier variante de nombre de comuna a su código DANE (1-16, 50-90)."""
    if pd.isna(nombre):
        return np.nan
    t = _sin_tildes(nombre).replace("?", "")
    m = re.search(r"(\d{1,2})", t)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 16 or n in (50, 60, 70, 80, 90):
            return n
    for k, v in CORREGIMIENTOS.items():
        if k in t:
            return v
    return np.nan


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def limpiar_accidentes() -> pd.DataFrame:
    v = pd.read_csv(C.RAW / "accidentes_victimas_medata.csv", low_memory=False)
    v = v.dropna(how="all")
    v = v[v["Radicado"].notna()].copy()
    v["lat"], v["lon"] = _num(v["Latitud"]), _num(v["Longitud"])
    v["fecha"] = pd.to_datetime(v["Fecha_incidente"], dayfirst=True, errors="coerce")
    hora = pd.to_datetime(v["Hora_incidente"], format="%H:%M:%S", errors="coerce")
    v["hora"] = hora.dt.hour
    v["muerto"] = (v["Gravedad_victima"] == "Muertos").astype(int)

    # Un incidente = un radicado. Se conserva el número de víctimas y si hubo muertos.
    g = v.groupby("Radicado")
    inc = g.agg(
        fecha=("fecha", "first"), hora=("hora", "first"),
        lat=("lat", "first"), lon=("lon", "first"),
        clase=("Clase_incidente", "first"),
        comuna_txt=("Comuna", "first"), barrio=("Barrio", "first"),
        victimas=("Gravedad_victima", "size"), muertos=("muerto", "sum"),
    ).reset_index()
    inc["Radicado"] = inc["Radicado"].astype(str)
    inc["anio"] = inc["fecha"].dt.year
    inc["comuna"] = inc["comuna_txt"].map(codigo_comuna)
    inc["barrio_n"] = inc["barrio"].map(_sin_tildes)

    n0 = len(inc)
    ok = inc["lat"].between(C.LAT_MIN, C.LAT_MAX) & inc["lon"].between(C.LON_MIN, C.LON_MAX)
    inc = inc[ok & inc["hora"].notna() & inc["fecha"].notna()].copy()
    inc["hora"] = inc["hora"].astype(int)
    print(f"Accidentes: {len(v):,} víctimas -> {n0:,} incidentes -> {len(inc):,} con coordenada y hora válidas")
    inc.to_parquet(C.PROC / "accidentes.parquet", index=False)
    return inc


ESTADOS_DESPACHO = {"Cerrado", "Completo", "PositivoFallido", "SinRecurso", "AtendidoGrupoDeSocorro"}


def limpiar_urgencias() -> pd.DataFrame:
    u = pd.read_csv(C.RAW / "urgencias_aph.csv", low_memory=False)
    u.columns = [_sin_tildes(c).replace(" ", "_") for c in u.columns]
    u["fecha"] = pd.to_datetime(u["fecha_del_incidente"], errors="coerce")
    u["anio"] = u["fecha"].dt.year
    nat = u["naturaleza_evento"].map(_sin_tildes).str.replace("?", "", regex=False)
    u["tipo"] = np.where(nat.str.contains("transito"), "accidente", "medica")
    u["comuna"] = u["comuna"].map(codigo_comuna)
    u["barrio_n"] = u["barrio"].map(_sin_tildes).str.replace("?", "", regex=False)
    u["estado"] = u["estado"].str.strip()
    u["despacho"] = u["estado"].isin(ESTADOS_DESPACHO)
    u["sin_recurso"] = u["estado"].eq("SinRecurso")
    cols = ["fecha", "anio", "tipo", "estado", "despacho", "sin_recurso", "comuna",
            "barrio", "barrio_n", "edad", "lugar_del_evento", "hospital_remitido", "finalizacion"]
    u = u[cols].copy()
    u["edad"] = pd.to_numeric(u["edad"], errors="coerce")
    for c in ["barrio", "lugar_del_evento", "hospital_remitido", "finalizacion"]:
        u[c] = u[c].astype("string")
    print(f"Urgencias: {len(u):,} registros; con despacho: {u['despacho'].sum():,}; "
          f"sin comuna: {u['comuna'].isna().sum():,}")
    u.to_parquet(C.PROC / "urgencias.parquet", index=False)
    return u


if __name__ == "__main__":
    limpiar_accidentes()
    limpiar_urgencias()
