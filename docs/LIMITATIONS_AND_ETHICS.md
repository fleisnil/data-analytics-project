# Limitations and responsible interpretation

1. **Forecast-based timing:** Stationboard prognosis and Actual data v2 can contain forecasts rather than directly measured event times.
2. **Coverage bias:** Journeys without real-time information may be absent. Missingness can differ by operator and mode.
3. **Station-panel design:** Selected hubs and urban stops do not represent every rural or local service.
4. **Repeated snapshots:** Live stationboards can observe the same journey multiple times. Stable keys and collection timestamps must be handled carefully.
5. **Weather resolution:** Open-Meteo values represent a grid cell, not a sensor on the track or at the platform.
6. **Unobserved factors:** Incidents, vehicle rotations, construction, passenger volumes and network dependencies can confound associations.
7. **Dependence:** Calls from the same journey, station and service day are not statistically independent. Station-clustered OLS errors address only one dimension; fewer than 30 clusters make uncertainty fragile. The ANOVA, chi-squared and correlation p-values remain exploratory.
8. **Multiple testing:** Several exploratory tests increase false-positive risk. The generated table includes Holm-adjusted p-values where computable. Report effect sizes, sample sizes and sparse expected-count warnings too.
9. **No causal language:** Prefer “associated with”, “higher/lower reported delay” and “conditional difference”. Do not say weather or a region caused a delay.
10. **Privacy:** The sources contain operational transport information and no intended personal data. Do not add passenger or employee identifiers.
11. **Different weather products:** Recent forecast API values and historical archive values have different provenance. Record the mix and retrieval dates; complete matches alone do not prove identical measurement quality.
12. **Model use:** Concurrent weather and latest reported delay are not always known before a trip. The forest is evaluated retrospectively, not validated as an operational advance prediction service.
