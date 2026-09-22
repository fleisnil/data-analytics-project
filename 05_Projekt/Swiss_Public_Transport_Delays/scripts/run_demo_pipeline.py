"""Run the complete development pipeline with a fresh live API snapshot."""

from sptdelays.clustering import run_clustering
from sptdelays.collect_live import collect_live
from sptdelays.collect_weather import collect_weather
from sptdelays.database import build_sqlite
from sptdelays.eda import run_eda
from sptdelays.geo import create_map
from sptdelays.modeling import run_models
from sptdelays.prepare import integrate_weather, prepare_transport


def main() -> None:
    collect_live()
    prepare_transport("live")
    collect_weather()
    integrate_weather()
    build_sqlite()
    run_eda()
    run_models()
    run_clustering()
    create_map()


if __name__ == "__main__":
    main()

