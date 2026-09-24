# Data sources and citations

## Primary transport data

**Open Data Platform Mobility Switzerland: Actual data v2**  
Dataset page: https://data.opentransportdata.swiss/en/dataset/ist-daten-v2  
Method notes: https://opentransportdata.swiss/en/cookbook/historic-and-statistics-cookbook/actual-data/

The daily files are an optional historical validation/extension. They contain scheduled times and actual values or the last available forecast. According to the publisher, records without real-time information can be absent and the data have limited suitability for exact punctuality measurement. If used, record the exact resource URLs and collection dates.

**Swiss public transport API**  
Documentation: https://transport.opendata.ch/docs.html

The `/locations` and `/stationboard` endpoints resolve stations and create the group-owned primary dataset through repeated snapshots. A single snapshot validates the workflow but is not a substitute for the multi-day final collection.

## Weather data

**Open-Meteo Historical Weather API**  
Documentation: https://open-meteo.com/en/docs/historical-weather-api

Hourly precipitation, snowfall, wind and temperature are retrieved for each selected station coordinate. Cite the exact Open-Meteo dataset/model shown in the final API response and acknowledge that grid-cell weather is not a measurement at the platform.

## Regional classification

**Swiss Federal Statistical Office: Swiss large regions / NUTS 2**  
Catalogue asset: https://dam-api.bfs.admin.ch/hub/api/dam/assets/32626994/master

The curated station panel assigns stations to the seven Swiss large regions. These assignments must be manually checked before the final analysis.

## Reproducibility record

Before submission, add:

- access date for every source;
- exact Actual data v2 service dates and resource URLs;
- API request variables, timezone and station coordinates;
- source licence/terms as shown on the provider pages;
- software versions from `uv.lock`;
- the final Git commit hash.
