# Limitations and responsible interpretation

1. **Forecast-based timing:** Stationboard prognosis and Actual data v2 can contain forecasts rather than directly measured event times.
2. **Coverage bias:** Journeys without real-time information may be absent. Missingness can differ by operator and mode.
3. **Station-panel design:** Selected hubs and urban stops do not represent every rural or local service.
4. **Repeated snapshots:** Live stationboards can observe the same journey multiple times. Stable keys and collection timestamps must be handled carefully.
5. **Weather resolution:** Open-Meteo values represent a grid cell, not a sensor on the track or at the platform.
6. **Unobserved factors:** Incidents, vehicle rotations, construction, passenger volumes and network dependencies can confound associations.
7. **Dependence:** Calls from the same journey and station are not statistically independent. Robust standard errors reduce but do not eliminate this concern.
8. **Multiple testing:** Several exploratory tests increase false-positive risk. Report effect sizes and exact p-values.
9. **No causal language:** Prefer “associated with”, “higher/lower reported delay” and “conditional difference”. Do not say weather or a region caused a delay.
10. **Privacy:** The sources contain operational transport information and no intended personal data. Do not add passenger or employee identifiers.
