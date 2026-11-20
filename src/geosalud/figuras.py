"""Figuras del paper (en inglés). Salida: results/figures/*.png y *.pdf"""
import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C
from .experimentos import BASE, N0, construir
from .simulacion import Datos, Escenario, simular

# Paleta de referencia (skill dataviz), roles fijos por entidad
AZUL, NARANJA, AQUA, AMARILLO = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
TINTA, TINTA2, GRIS = "#0b0b0b", "#52514e", "#d9d8d4"
COLOR = {"Bomberos (actual aprox.)": NARANJA, "p-mediana": AQUA,
         "MEXCLP equitativo": AZUL, "MEXCLP": AMARILLO}
NOMBRE_EN = {"Bomberos (actual aprox.)": "Fire stations (current proxy)",
             "p-mediana": "p-median", "MEXCLP equitativo": "Equity-constrained MEXCLP",
             "MEXCLP": "MEXCLP", "K-Means ponderado": "Weighted k-means",
             "MEXCLP dinámico": "Time-dependent MEXCLP"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRIS,
    "axes.labelcolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#ecebe8", "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "figure.dpi": 110,
})


def guardar(fig, nombre):
    for ext in ("png", "pdf"):
        fig.savefig(C.FIG / f"{nombre}.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def fig_brecha():
    e = pd.read_csv(C.TAB / "E0_brecha.csv").set_index("caso")["brecha"]
    total = e["Calibrado (actual)"]
    geo = e["Igual regulación + FIFO"]
    reg = total - e["Igual regulación"]
    pri = total - e["Sin prioridad (FIFO)"]
    resto = total - geo - reg - pri
    partes = [("Geography\n(where calls occur)", geo), ("Queue priority\n(trauma first)", pri),
              ("Longer phone\ntriage", reg)]
    # la interacción entre efectos es pequeña (< 0,2 min) y se reporta en el texto
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    x0 = 0
    for i, (lab, v) in enumerate(partes):
        ax.barh(0, v, left=x0, color=[AZUL, AQUA, NARANJA, GRIS][i], height=0.5,
                edgecolor="white", linewidth=2)
        ax.text(x0 + v / 2, 0, f"{v:.1f} min", ha="center", va="center", color="white",
                fontweight="bold", fontsize=10)
        ax.text(x0 + v / 2, 0.42, lab, ha="center", va="bottom", color=TINTA2, fontsize=9)
        x0 += v
    ax.set_xlim(0, x0 * 1.02)
    ax.set_ylim(-0.4, 1.1)
    ax.set_yticks([])
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Extra response time of medical emergencies vs. traffic crashes (min)")
    ax.set_title(f"Medical emergencies wait {total:.1f} min longer; geography explains only "
                 f"{geo:.1f}", loc="left", fontsize=11, color=TINTA)
    guardar(fig, "fig1_descomposicion_brecha")


def fig_flota():
    e = pd.read_csv(C.TAB / "E2_flota_ubicacion.csv")
    e = e[~e.estrategia.str.contains("t_hosp")]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for nom in ("Bomberos (actual aprox.)", "p-mediana", "MEXCLP equitativo"):
        d = e[e.estrategia == nom].sort_values("flota")
        ax.fill_between(d.flota, d.resp_media_lo, d.resp_media_hi, color=COLOR[nom], alpha=0.15, lw=0)
        ax.plot(d.flota, d.resp_media, color=COLOR[nom], lw=2, marker="o", ms=4, label=NOMBRE_EN[nom])
    ref = e[(e.estrategia == "Bomberos (actual aprox.)") & (e.flota == N0)].resp_media.iloc[0]
    ax.axvline(N0, color=TINTA2, lw=1, ls="--")
    ax.text(N0 + 0.2, 38, "Official fleet\n(17 ambulances)", color=TINTA2, fontsize=8.5)
    ax.axhline(ref, color=GRIS, lw=1)
    ax.set_ylim(8, 45)
    ax.set_xticks(range(13, 31, 1), [str(i) if i % 2 == 1 else "" for i in range(13, 31)])
    ax.set_xlabel("Ambulances in service")
    ax.set_ylabel("Mean response time (min)")
    ax.set_title("Below 17 ambulances the system collapses; good siting is worth extra units",
                 loc="left", fontsize=11, color=TINTA)
    ax.legend(loc="upper right")
    guardar(fig, "fig3_flota_vs_ubicacion")


def fig_palancas():
    e = pd.read_csv(C.TAB / "E2_flota_ubicacion.csv")
    f = e[~e.estrategia.str.contains("t_hosp")]
    h = e[e.estrategia.str.contains("t_hosp")]
    b = lambda n: f[(f.estrategia == "Bomberos (actual aprox.)") & (f.flota == n)].resp_media.iloc[0]
    base = b(N0)
    mex = f[(f.estrategia == "MEXCLP equitativo") & (f.flota == N0)].resp_media.iloc[0]
    th = lambda est, t: h[(h.estrategia == est + " | t_hosp") & (h.t_hosp == t)].resp_media.iloc[0]
    filas = [
        ("+1 ambulance (fire stations)", b(N0 + 1)),
        ("Relocate the 17 (equity MEXCLP)", mex),
        ("+3 ambulances (fire stations)", b(N0 + 3)),
        (f"Hospital handover {BASE['t_hosp']:.0f} → 90 min", th("Bomberos (actual aprox.)", 90)),
        ("Relocate + handover 90 min", th("MEXCLP equitativo", 90)),
    ]
    df = pd.DataFrame(filas, columns=["palanca", "resp"])
    df["delta"] = df.resp - base
    df = df.sort_values("delta", ascending=False)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    cols = [AZUL if "Relocate" in p or "handover" in p else NARANJA for p in df.palanca]
    ax.barh(df.palanca, df.delta, color=cols, height=0.55, edgecolor="white")
    for y, (d, r) in enumerate(zip(df.delta, df.resp)):
        ax.text(d - 0.1, y, f"{d:+.1f} min  ({r:.1f})", ha="right", va="center", color=TINTA, fontsize=9)
    ax.set_xlim(df.delta.min() * 1.55, 0)
    ax.axvline(0, color=TINTA2, lw=1)
    ax.set_xlabel(f"Change in mean response time vs. current proxy ({base:.1f} min)")
    ax.set_title("Hospital handover time is a bigger lever than fleet or siting", loc="left",
                 fontsize=11, color=TINTA)
    ax.grid(axis="y", visible=False)
    guardar(fig, "fig4_palancas")


def fig_validacion():
    c = pd.read_csv(C.TAB / "E4_sin_recurso_comuna.csv")
    from scipy.stats import spearmanr
    rho = spearmanr(c.modelo, c.real_2022).statistic
    com = gpd.read_file(C.PROC / "comunas.geojson")
    nom = dict(zip(com.comuna, com.name.str.replace(r"Comuna \d+ - ", "", regex=True)))
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    ax.scatter(c.real_2022 * 100, c.modelo * 100, s=36, color=AZUL, edgecolor="white", lw=1.5, zorder=3)
    m = max(c.real_2022.max(), c.modelo.max()) * 105
    ax.plot([0, m], [0, m], color=GRIS, lw=1, zorder=1)
    for _, r in c.iterrows():
        if r.comuna in (10, 14, 16, 7, 3):
            ax.annotate(nom.get(r.comuna, r.comuna), (r.real_2022 * 100, r.modelo * 100),
                        xytext=(5, -3), textcoords="offset points", fontsize=8, color=TINTA2)
    ax.set_xlabel("Observed 'no resource available' cases, 2022 (% by district)")
    ax.set_ylabel("Simulated calls finding no idle ambulance (%)")
    ax.set_title(f"Out-of-calibration check: Spearman ρ = {rho:.2f}", loc="left",
                 fontsize=11, color=TINTA)
    guardar(fig, "fig5_validacion_sin_recurso")


def _por_comuna(D, nombre, reps=20):
    b = construir(D, nombre, N0, Escenario(), 0.58)
    sims = pd.concat([simular(D, Escenario(dias=30, **BASE), b, s) for s in range(reps)])
    return sims.groupby("comuna").respuesta.mean(), b


def fig_equidad_y_mapa(D):
    act, b_act = _por_comuna(D, "Bomberos (actual aprox.)")
    pro, b_pro = _por_comuna(D, "MEXCLP equitativo")
    com = gpd.read_file(C.PROC / "comunas.geojson")
    nom = dict(zip(com.comuna, com.name.str.replace(r"Comuna \d+ - ", "", regex=True)))
    df = pd.DataFrame({"actual": act, "propuesta": pro}).dropna()
    df.to_csv(C.TAB / "respuesta_por_comuna.csv")
    df = df.sort_values("actual")
    mejora = int((df.propuesta < df.actual).sum())
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    y = np.arange(len(df))
    ax.hlines(y, df.propuesta, df.actual, color=GRIS, lw=2)
    ax.scatter(df.actual, y, color=NARANJA, s=36, zorder=3, label=NOMBRE_EN["Bomberos (actual aprox.)"])
    ax.scatter(df.propuesta, y, color=AZUL, s=36, zorder=3, label=NOMBRE_EN["MEXCLP equitativo"])
    ax.set_yticks(y, [nom.get(c, c) for c in df.index], fontsize=8.5)
    ax.set_xscale("log")
    from matplotlib.ticker import NullFormatter
    ax.set_xticks([8, 10, 15, 20, 30, 50, 80], ["8", "10", "15", "20", "30", "50", "80"])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Mean response time (min, log scale)")
    ax.set_title(f"Relocation improves {mejora} of {len(df)} districts", loc="left", fontsize=11, color=TINTA)
    ax.legend(loc="lower right", fontsize=8.5)
    ax.grid(axis="y", visible=False)
    guardar(fig, "fig6_equidad_comunas")

    # mapa: demanda + bases actuales vs propuestas
    g = gpd.read_file(C.PROC / "grilla.geojson")
    E = Escenario()
    g["dem"] = E.lam_acc * g.w_acc_tr + E.lam_med * g.w_med_tr
    fig, axs = plt.subplots(1, 2, figsize=(9.6, 5.4), sharex=True, sharey=True)
    for ax, b, tit, col in ((axs[0], b_act, "Current proxy: fire stations", NARANJA),
                            (axs[1], b_pro, "Proposed: equity-constrained MEXCLP", AZUL)):
        com.boundary.plot(ax=ax, color=GRIS, lw=0.6)
        gg = g[g.dem > 0]
        gg.plot(ax=ax, column="dem", cmap="Blues", scheme=None, vmax=gg.dem.quantile(0.98), lw=0)
        pts = pd.Series(np.asarray(b)).value_counts()
        xy = g.set_index("celda").loc[pts.index, ["xm", "ym"]]
        ax.scatter(xy.xm, xy.ym, s=40 + 45 * (pts.values - 1), color=col, edgecolor="white", lw=1.5, zorder=4)
        ax.set_title(tit, loc="left", fontsize=10, color=TINTA)
        x0, y0, x1, y1 = gg.total_bounds
        ax.set_xlim(x0 - 800, x1 + 800)
        ax.set_ylim(y0 - 800, y1 + 800)
        ax.set_axis_off()
    fig.suptitle("Ambulance bases (dot size = ambulances) over expected demand (darker = more calls)",
                 x=0.02, y=0.98, ha="left", fontsize=11, color=TINTA)
    guardar(fig, "fig2_mapa_bases")
    return df, mejora


if __name__ == "__main__":
    D = Datos()
    fig_brecha()
    fig_flota()
    fig_palancas()
    fig_validacion()
    df, mejora = fig_equidad_y_mapa(D)
    print("comunas que mejoran:", mejora, "de", len(df))
