import tempfile, unittest, sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.path import Path as PlotPath
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
        bubbles = {}
        for city, point, size in zip(hubs.city, ax.collections[0].get_offsets(),
                                     ax.collections[0].get_sizes()):
            x, y = ax.transData.transform(point)
            radius = renderer.points_to_pixels(np.sqrt(size) / 2 + .35)
            bubbles[city] = (np.array([x, y]), radius)
        lines = {line.get_gid(): PlotPath(ax.transData.transform(line.get_xydata()))
                 for line in ax.lines}
        self.assertEqual(set(lines), {f"hub-label:{city}" for city in hubs.city})
        frame = ax.bbox.padded(-renderer.points_to_pixels(5))
        label_boxes = {}
        for label in ax.texts:
            city = label.get_text().splitlines()[0]
            box = label.get_window_extent(renderer).padded(renderer.points_to_pixels(1.2))
            self.assertTrue(frame.contains(box.x0, box.y0) and frame.contains(box.x1, box.y1))
            self.assertFalse(any(box.overlaps(other) for other in label_boxes.values()))
            for center, radius in bubbles.values():
                self.assertGreater(np.linalg.norm(center - np.clip(center, box.min, box.max)), radius)
            label_boxes[city] = box

        for city, box in label_boxes.items():
            link = lines[f"hub-label:{city}"]
            start, end = link.vertices
            center, radius = bubbles[city]
            self.assertAlmostEqual(np.linalg.norm(start - center) - radius,
                                   renderer.points_to_pixels(.8), places=5)
            np.testing.assert_allclose(end, np.clip(center, box.min, box.max), atol=1e-5)
            self.assertLessEqual(np.linalg.norm(end - start), renderer.points_to_pixels(9))
            self.assertFalse(any(link.intersects_bbox(other, filled=False)
                                 for name, other in label_boxes.items() if name != city))

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
