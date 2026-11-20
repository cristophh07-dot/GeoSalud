# GeoSalud — ¿Ubicación o flota? Ambulancias en Medellín

**Gemelo digital del programa público de atención prehospitalaria (APH) de Medellín para decidir dónde ubicar las ambulancias, cuántas hacen falta y qué tanto pesa el tiempo que pasan retenidas en las clínicas.**

> *English summary.* We build a calibrated discrete-event simulation of Medellín's public
> EMS (17 ambulances) using open data: 170,737 geocoded traffic crashes (2014–2021),
> 103,346 dispatched prehospital cases (2018–2022), a time-dependent metropolitan road
> network and the city's own response-time dashboard. Medical emergencies wait ~7.5 min
> longer than crashes; geography explains only ~2.3 min of that gap. An equity-constrained
> MEXCLP relocation cuts mean response time by 1.5 min (more than adding one ambulance) and
> improves 19 of 21 districts, but reducing hospital handover time is the largest single lever.

## Resultados principales

| | Actual (aprox.: bases en estaciones de bomberos) | Propuesta (MEXCLP equitativo) |
| --- | --- | --- |
| Tiempo medio de respuesta | 16,9 min | 15,3 min |
| Percentil 90 | 27,7 min | 25,3 min |
| Accidentes de tránsito | 13,6 min | 12,2 min |
| Emergencias médicas | 21,1 min | 19,4 min |
| Llamadas atendidas en ≤ 15 min | 64 % | 71 % |
| Corregimientos (promedio) | 41,3 min | 37,1 min |

Simulación con la flota oficial de 17 ambulancias, 20 réplicas de 30 días y demanda **fuera de muestra** (2020–2021). El modelo calibrado reproduce el tablero oficial de 2026 (13,6 frente a 13,7 min en accidentes; 20,9 frente a 20,4 en emergencias médicas) y la tasa de casos *SinRecurso* de 2022 (7,3 % frente a 6,7 %).

![Descomposición de la brecha](results/figures/fig1_descomposicion_brecha.png)

- **La brecha no es geográfica.** Las emergencias médicas esperan unos 7,5 minutos más que los accidentes. Que ocurran en zonas más lejanas explica 2,3 minutos; la prioridad de los accidentes en la cola, otros 2,3; y una regulación telefónica más larga, 3,1.
- **El sistema está al borde.** Con 15 ambulancias el promedio sube a 23 minutos; con 13, a 38.
- **Reubicar vale más que una ambulancia nueva.** MEXCLP equitativo con 17 ambulancias (15,3 min) supera a las bases de bomberos con 18 (15,5 min). El MEXCLP sin restricción baja aún más el promedio (14,7 min), pero empeora los corregimientos (45 min); la versión equitativa los mejora.
- **El método del proyecto original empeora el servicio.** El K-Means ponderado da 19,9 minutos, porque dispersa la flota en 17 sitios cuando el sistema está ocupado el 59 % del tiempo.
- **La palanca más grande está en las clínicas.** Bajar la entrega del paciente de 150 a 90 minutos ahorra 3,5 minutos, más que agregar 3 ambulancias (3,0). Junto con la reubicación, el promedio llega a 11,7 minutos (−31 %) y el de las emergencias médicas baja de 21,2 a 14,6.
- **Validación externa.** La distribución por comuna de los casos sin ambulancia disponible que predice el modelo coincide con los casos *SinRecurso* reales de 2022 (Spearman ρ = 0,92), un dato que no se usó para calibrar.

![Flota vs. ubicación](results/figures/fig3_flota_vs_ubicacion.png)

## Método

1. **Demanda** (`demanda.py`): grilla de 300 m. Los accidentes se ubican por coordenada, un registro por incidente. Las emergencias médicas se reparten dentro de su barrio. Para construir se usan los datos de 2014–2019 y para evaluar los de 2020–2021.
2. **Tiempos de viaje** (`tiempos.py`): grafo dirigido de OpenStreetMap del Valle de Aburrá (Medellín y municipios vecinos) con velocidades por tipo de vía, ajustadas por hora con Google Traffic (2017–2020). Hay cuatro franjas horarias y las distancias se calculan con Dijkstra.
3. **Simulación** (`simulacion.py`): eventos discretos con llegadas Poisson por hora, regulación, cola con prioridad para el trauma, viaje, escena, traslado a la IPS receptora real y regreso a la base.
4. **Calibración** (`calibracion.py`): búsqueda en grilla del tiempo de entrega en la IPS, la velocidad y la regulación médica contra tres objetivos observados.
5. **Estrategias** (`estrategias.py`): bomberos (operación actual aproximada), K-Means ponderado, p-mediana, MEXCLP (Daskin, 1983), MEXCLP con cobertura de corregimientos y MEXCLP por franja horaria.
6. **Experimentos** (`experimentos.py`): E0 brecha, E1 estrategias, E2 flota × ubicación × tiempo en IPS, E3 sensibilidad, E4 validación.

## Cómo reproducir

```bash
pip install -r requirements.txt
# copiar los datos crudos según data/README.md
python scripts/descargar_red_metropolitana.py   # red vial del Valle de Aburrá
python scripts/run_all.py
```

Todo el pipeline corre en unos 5 minutos en un portátil.

## Limitaciones

- **Ubicación de las bases actuales.** No es pública; se aproxima con las estaciones de bomberos, igual que en Castañeda y Villegas (2017).
- **Hora de las emergencias médicas.** No está en los datos abiertos; se usa el perfil de los accidentes y se prueban perfiles alternativos en E3. El orden de las estrategias no cambia.
- **Velocidades.** El perfil horario sale de Google Traffic en 12 corredores (2017–2020) y se aplica a toda la red; las vías locales se congestionan menos que las arterias (supuesto).
- **Tipo de ambulancia.** Las 2 TAM (medicalizadas) se modelan igual que las 15 TAB, y las motos no se incluyen.
- **Tiempo en la IPS.** Los 150 minutos son un parámetro calibrado, no medido. Representan todo el tiempo que la ambulancia no está disponible después de la escena.

## Referencias clave

- Castañeda, C. P., y Villegas, J. G. (2017). Analyzing the response to traffic accidents in Medellín, Colombia, with facility location models. *IATSS Research*, 41(1), 47–56.
- Daskin, M. S. (1983). A maximum expected covering location model. *Transportation Science*, 17(1), 48–70.
- Secretaría de Salud de Medellín. Tablero "Atención prehospitalaria en emergencias médicas y accidentes" (MEData).

## Autor

Cristopher Corrales Boada — Ingeniería en Ciencia de Datos, Instituto Tecnológico Metropolitano (ITM), Medellín.
