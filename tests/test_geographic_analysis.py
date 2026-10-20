import tempfile, unittest, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import geographic_analysis

class GeographicAnalysisTest(unittest.TestCase):
    def test_summary_and_map(self):
        data=pd.DataFrame({"city":["Bern","Bern","Zürich","Zürich"],
                           "transport_mode":["rail","bus","rail","tram"],
                           "predicted_delay_minutes":[0.0,6.0,1.0,2.0]})
        coords=pd.DataFrame({"city":["Bern","Zürich"],"latitude":[46.94809,47.37818],
                             "longitude":[7.43913,8.54019],"reference_stop":["Bern","Zürich HB"],
                             "coordinate_system":["WGS84","WGS84"]})
        summary=geographic_analysis.build_city_summary(data,coords)
        self.assertEqual(len(summary),2)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"map.png"
            geographic_analysis.plot_geographic_delay_map(summary,path)
            self.assertTrue(path.exists())

if __name__=="__main__": unittest.main()
