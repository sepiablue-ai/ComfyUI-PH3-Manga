"""Behavior checks for layout assets, guides, and font lettering (no model inference)."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ph3_manga_tests", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)
from ph3_manga_tests.fonts import resolve_font
from ph3_manga_tests.lettering import _cells, layout_columns, ruby_spans
from ph3_manga_tests.nodes import DATA, PH3MangaBalloonGuide, PH3MangaLayout, PH3MangaLettering, layouts


class LayoutTests(unittest.TestCase):
    def test_catalog_assets_and_resolution(self):
        self.assertEqual(len(layouts()), 196)
        for key, item in layouts().items():
            with self.subTest(layout=key), Image.open(DATA / "layouts" / f"{key}.webp") as image:
                self.assertTrue(2 <= len(item["panels"]) <= 6)
                self.assertEqual(image.size, (1024, 1536))
                self.assertFalse(image.info.get("exif") or image.info.get("xmp"))
        page, width, height, count, info = PH3MangaLayout().run("normal_3_01")
        self.assertEqual((width, height, count), (1664, 2496, 3))
        self.assertEqual(tuple(page.shape), (1, 1536, 1024, 3))
        self.assertEqual(json.loads(info)["id"], "normal_3_01")


class GuideTests(unittest.TestCase):
    def test_tail_and_text_region_without_modifying_input(self):
        original = torch.ones((1, 200, 200, 3))
        element = {"bbox": [200, 200, 600, 600], "type": "text", "text": "雨", "desc": '{"tail":[800,400]}'}
        guide, texts = PH3MangaBalloonGuide().run(original, [element], 0.7, 2)
        self.assertEqual(tuple(guide.shape), tuple(original.shape))
        self.assertTrue(torch.all(original == 1))
        self.assertTrue(torch.any(guide < 1))
        self.assertAlmostEqual(texts[0]["bbox"][0], 260)
        self.assertEqual(texts[0]["text"], "雨")
        self.assertTrue(torch.any(guide[0, 77:84, 156:164] < 0.5))

    def test_pixels_outside_balloons_are_unchanged(self):
        image = torch.rand((1, 300, 200, 3), generator=torch.Generator().manual_seed(1))
        element = {"bbox": [100, 100, 400, 500], "desc": '{"tail":[300,600]}'}
        guide, _ = PH3MangaBalloonGuide().run(image, [element], 0.7, 2)
        changed = torch.any(guide != image, dim=-1)[0]
        ys, xs = torch.nonzero(changed, as_tuple=True)
        # Ellipse spans x 20..100, y 30..120 and the tail reaches (60,180); outline adds 2 px.
        self.assertGreaterEqual(int(xs.min()), 20 - 3)
        self.assertLessEqual(int(xs.max()), 100 + 3)
        self.assertGreaterEqual(int(ys.min()), 30 - 3)
        self.assertLessEqual(int(ys.max()), 180 + 3)
        self.assertTrue(torch.equal(guide[0, 200:], image[0, 200:]))
        self.assertTrue(torch.allclose(guide[0, 75, 60], torch.ones(3)))

    def test_invalid_geometry_and_tail(self):
        image = torch.ones((1, 100, 100, 3))
        for element in [{"bbox": [20, 30, 20, 40]}, {"bbox": [20, 30, 80, 90], "desc": '{"tail":[-1,500]}'}]:
            with self.assertRaises(ValueError):
                PH3MangaBalloonGuide().run(image, [element], 0.7, 2)


class LetteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.kana = resolve_font("auto", "kana")
            cls.kanji = resolve_font("auto", "kanji")
        except ValueError as exc:
            raise unittest.SkipTest(str(exc))

    def test_punctuation_is_in_upper_right_of_its_cell(self):
        image = torch.ones((1, 256, 256, 3))
        for punctuation in ("、", "。"):
            with self.subTest(punctuation=punctuation):
                output, _ = PH3MangaLettering().run(image, self.kana, self.kanji, 0.05,
                    [{"bbox": [200, 200, 800, 800], "text": punctuation}])
                ys, xs = np.where(np.any(output[0].numpy() < 0.9, axis=2))
                self.assertGreater(xs.mean(), 128)
                self.assertLess(ys.mean(), 128)

    def test_explicit_columns_ruby_and_unchanged_artwork(self):
        image = torch.rand((1, 256, 256, 3), generator=torch.Generator().manual_seed(0))
        text = "病める時も\n健やかなる時も、"
        element = {"bbox": [100, 100, 900, 900], "type": "text", "text": text}
        output, info = PH3MangaLettering().run(image, self.kana, self.kanji, 0.04, [element], '{"時":"とき"}')
        record = json.loads(info)[0]
        self.assertEqual(record["columns"], ["病める時も", "健やかなる時も、"])
        baseline = (image[0].numpy() * 255).clip(0, 255).astype(np.uint8)
        rendered = (output[0].numpy() * 255).clip(0, 255).astype(np.uint8)
        mask = np.ones(baseline.shape[:2], dtype=bool)
        mask[21:235, 21:235] = False
        self.assertTrue(np.array_equal(baseline[mask], rendered[mask]))
        self.assertTrue(np.any(baseline != rendered))

    def test_ruby_rows_count_tatechuyoko_as_one_cell(self):
        cells = _cells("え！？雨")
        self.assertEqual(cells, ["え", "！？", "雨"])
        self.assertEqual(ruby_spans(cells, "雨"), [(2, 1)])
        self.assertEqual(ruby_spans(cells, "え！？"), [(0, 2)])
        self.assertEqual(ruby_spans(cells, "！"), [])  # starts inside a cell boundary but ends mid-cell

    def test_empty_input_and_invalid_ruby(self):
        image = torch.ones((1, 32, 32, 3))
        output, info = PH3MangaLettering().run(image, "auto", "auto", 0.02, [])
        self.assertIs(output, image)
        self.assertEqual(info, "[]")
        for bad in ('{"雨":""}', "[]", '{"雨":42}'):
            with self.assertRaises(ValueError):
                PH3MangaLettering().run(image, "auto", "auto", 0.02, [], bad)


if __name__ == "__main__":
    unittest.main()
