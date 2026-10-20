import tempfile,unittest,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import database_duckdb

class DuckDBDatabaseTest(unittest.TestCase):
    def transport(self):
        rows=[]
        for idx,t in enumerate(["2026-10-01T10:00:00Z","2026-10-01T10:50:00Z"],start=1):
            rows.append({"operating_day":"2026-10-01","journey_ref":f"J{idx}","station_id":"station","station_name":"Test",
                         "station_type":"rail","city":"Zürich","transport_mode":"rail","product_category":"IC",
                         "public_code":"IC1","line":"IC1","train_number":str(idx),"origin":"A","destination":"B",
                         "collection_timestamp":t,"scheduled_departure":"2026-10-01T11:00:00Z",
                         "estimated_departure":"2026-10-01T11:01:00Z","predicted_delay_minutes":1.0,
                         "minutes_until_departure":10.0,"is_predicted_delayed_5min":False,"hour":11,
                         "weekday":"Thursday","weekend":False})
        return pd.DataFrame(rows)
    def weather(self):
        return pd.DataFrame([{"city":"Zürich","weather_station_abbr":"SMA","weather_station_name":"Zürich / Fluntern",
                              "reference_timestamp":"2026-10-01T09:50:00Z","temperature_c":15.0,
                              "precipitation_mm_10min":0.0,"relative_humidity_pct":60.0,"wind_speed_kmh_10min":5.0,
                              "wind_gust_kmh":10.0,"station_pressure_hpa":970.0},
                             {"city":"Zürich","weather_station_abbr":"SMA","weather_station_name":"Zürich / Fluntern",
                              "reference_timestamp":"2026-10-01T10:05:00Z","temperature_c":16.0,
                              "precipitation_mm_10min":0.0,"relative_humidity_pct":58.0,"wind_speed_kmh_10min":6.0,
                              "wind_gust_kmh":11.0,"station_pressure_hpa":970.0}])
    def test_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"test.duckdb"
            database_duckdb.create_database(self.transport(),self.weather(),database_path=path)
            v=database_duckdb.validate_database(path)
            self.assertEqual(v["transport_rows"],2); self.assertEqual(v["joined_rows"],2)
            self.assertEqual(v["weather_matched_rows"],1); self.assertEqual(v["future_weather_matches"],0)

if __name__=="__main__": unittest.main()
