# Current Findings — 2026-10-08 analysis snapshot

This document records the current analysis snapshot for the presentation draft. The automated collection may continue, so all numbers should be regenerated before the final submission.

## Research question

**Which operational, temporal and weather-related factors are associated with public transport delays in Switzerland, and how do these associations differ across regions and transport modes?**

## Data quality and sample

- 17,591 raw OJP rows were collected.
- 3,347 unique journey/stop observations were retained in the 5–15 minute pre-departure window.
- 3,334 of 3,347 selected observations matched weather data, a 99.61% match rate.
- The analysis covers eight regions and the bus, rail and tram modes in the currently selected modelling sample.
- Mean predicted delay is 0.505 minutes, median 0.2 minutes, and only 1.14% of observations have a predicted delay of at least five minutes.

## Statistical evidence

Operational and regional differences are clearer than the observed weather effects.

- Transport mode: Kruskal-Wallis p < 0.001, epsilon-squared = 0.141.
- Region/city: Kruskal-Wallis p < 0.001, epsilon-squared = 0.074.
- The five-minute transport-mode Chi-square test is significant, but the association is small (Cramer's V = 0.050).
- The city Chi-square test should not be interpreted because the expected-count assumption is violated.

Within-city weather correlations are statistically detectable but weak:

- temperature: Spearman rho = 0.268
- relative humidity: rho = -0.228
- wind speed: rho = 0.137
- wind gust: rho = 0.154
- precipitation: rho = 0.025, not significant

The wet-vs-dry comparison is also not significant (p = 0.661), with only 10 wet city-weather groups.

## Regression model

The five-minute classification target is too imbalanced for the primary model, so the project uses regression on `predicted_delay_minutes`.

Chronological test-set performance:

| Model | MAE | RMSE | R² | MAE change vs baseline |
| --- | ---: | ---: | ---: | ---: |
| Median baseline | 0.6782 | 1.6613 | -0.0578 | 0.0% |
| Linear regression | 0.7015 | 1.6230 | -0.0096 | -3.43% |
| Random forest | 0.7583 | 1.6408 | -0.0318 | -11.80% |
| Gradient boosting (absolute-error loss) | **0.6206** | 1.6822 | -0.0845 | **+8.49%** |

Gradient boosting improves the primary metric MAE, but its RMSE is slightly worse than the baseline and R² remains negative. The model therefore improves typical absolute error without explaining the larger/unusual delays well.

## Differences by region and mode

Gradient-boosting MAE improvement relative to the median baseline:

### Regions

- St. Gallen: 22.1%
- Bern: 20.2%
- Zürich: 17.7%
- Lugano: 14.1%
- Luzern: 6.6%
- Basel: 3.0%
- Genève: 2.9%
- Lausanne: 2.9%

### Transport modes

- rail: 14.4%
- bus: 8.4%
- tram: 0.7%

## Model feature importance

For the best-MAE model, the leading permutation-importance variables are:

1. station type
2. city
3. transport mode
4. product category

Weather variables have approximately zero incremental permutation importance in the current best model. This does not contradict the weak statistical weather correlations: a variable can be associated with delay without materially improving prediction once the operational and regional features are already included.

## Presentation conclusion

**Operational and regional factors are more informative than the observed weather variables for short-term OJP departure-delay estimates.** Transport mode and region show clear group differences, while weather effects are weak and precipitation is not supported in the current sample.

The best regression model improves MAE by about 8.5% over a simple median baseline, with stronger improvements for rail and in selected regions such as St. Gallen, Bern and Zürich. However, negative or near-zero R² values show that larger and unusual delays remain difficult to predict.

The results describe associations in the observed central-hub sample. They do not establish causal effects, and OJP `EstimatedTime` is a real-time estimate rather than a realised final delay.
