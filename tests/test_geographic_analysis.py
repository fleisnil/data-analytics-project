import tempfile, unittest, sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.transforms import Bbox
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

    def test_all_real_hub_labels_clear_bubbles_other_labels_and_plot_edges(self):
        path = Path(__file__).resolve().parents[1] / geographic_analysis.COORDINATE_PATH
        hubs = pd.read_csv(path).assign(
            observations=range(100, 900, 100),
            mean_predicted_delay_min=np.linspace(.35, .9, 8),
        )
        fig = geographic_analysis.build_geographic_delay_figure(hubs)
        self.addCleanup(plt.close, fig)
        fig.canvas.draw()
        ax = fig.axes[0]
        renderer = fig.canvas.get_renderer()
        self.assertEqual({label.get_text().splitlines()[0] for label in ax.texts}, set(hubs.city))
        bubbles = []
        for point, size in zip(ax.collections[0].get_offsets(), ax.collections[0].get_sizes()):
            x, y = ax.transData.transform(point)
            radius = renderer.points_to_pixels(np.sqrt(size) / 2 + .35)
            bubbles.append(Bbox.from_extents(x - radius, y - radius, x + radius, y + radius))
        frame = ax.bbox.padded(-renderer.points_to_pixels(5))
        prior = []
        for label in ax.texts:
            box = label.get_window_extent(renderer).padded(renderer.points_to_pixels(1.2))
            self.assertTrue(frame.contains(box.x0, box.y0) and frame.contains(box.x1, box.y1))
            self.assertFalse(any(box.overlaps(other) for other in [*bubbles, *prior]))
            prior.append(box)

    def test_crowded_hubs_fall_back_to_a_separate_key_without_losing_names(self):
        names = [f"Hub {index}" for index in range(30)]
        hubs = pd.DataFrame({
            "city": names, "latitude": 47.0, "longitude": 8.0,
            "observations": 100, "mean_predicted_delay_min": .5,
        })
        fig = geographic_analysis.build_geographic_delay_figure(hubs)
        self.addCleanup(plt.close, fig)
        self.assertEqual(len(fig.legends), 1)
        direct = [label.get_text().splitlines()[0] for label in fig.axes[0].texts]
        key = [label.get_text().split(" — ")[0] for label in fig.legends[0].texts]
        self.assertCountEqual(direct + key, names)

if __name__=="__main__": unittest.main()
