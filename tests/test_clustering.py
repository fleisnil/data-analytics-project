import unittest,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import clustering

class ClusteringTest(unittest.TestCase):
    def make_data(self):
        rows=[]
        for i in range(90):
            high=i>=45
            rows.append({"city":"Lausanne" if high else "Bern","transport_mode":"bus" if high else "rail",
                         "station_type":"local" if high else "rail","predicted_delay_minutes":4+(i%5)*.2 if high else .2+(i%5)*.05,
                         "hour":18 if high else 8,"temperature_c":25 if high else 11,
                         "precipitation_mm_10min":.4 if high else 0,"relative_humidity_pct":70 if high else 50,
                         "wind_speed_kmh_10min":12 if high else 4,"wind_gust_kmh":20 if high else 8,
                         "station_pressure_hpa":955 if high else 970})
        return pd.DataFrame(rows)
    def test_kmeans(self):
        work,x,features=clustering.prepare_clustering_features(self.make_data())
        scores,best_k=clustering.select_k(x,candidates=range(2,5))
        self.assertIn(best_k,[2,3,4]); self.assertEqual(len(work),90); self.assertIn("hour_sin",features)
        model,labels=clustering.fit_kmeans(x,best_k)
        self.assertEqual(len(labels),90); self.assertEqual(model.n_clusters,best_k)

if __name__=="__main__": unittest.main()
