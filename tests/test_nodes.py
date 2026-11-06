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
from ph3_manga_tests.fonts import load_font, resolve_font
from ph3_manga_tests.lettering import _cells, layout_columns, ruby_spans, tatechuyoko
from ph3_manga_tests.page import PH3MangaPage, PH3MangaPanel, left_to_right_order
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

    def test_tatechuyoko_fits_one_cell_tightly(self):
        size = 80
        font = load_font(self.kanji, size)
        for pair in ("！！", "！？", "!?"):
            with self.subTest(pair=pair):
                mark = np.asarray(tatechuyoko(pair, font, size)) > 64
                self.assertLessEqual(mark.shape[1], size * 0.9)
                cols = np.where(mark.any(axis=0))[0]
                gaps = np.diff(cols) - 1
                self.assertLessEqual(int(gaps.max(initial=0)), size * 0.12)  # 2字の間が詰まっている

    def test_empty_input_and_invalid_ruby(self):
        image = torch.ones((1, 32, 32, 3))
        output, info = PH3MangaLettering().run(image, "auto", "auto", 0.02, [])
        self.assertIs(output, image)
        self.assertEqual(info, "[]")
        for bad in ('{"雨":""}', "[]", '{"雨":42}'):
            with self.assertRaises(ValueError):
                PH3MangaLettering().run(image, "auto", "auto", 0.02, [], bad)


class PageTests(unittest.TestCase):
    def panel(self, actors, *lines, scene="人物1 waves."):
        kw = {"場面": scene, "登場人物": actors, "話者1": "セリフなし", "セリフ1": "", "話者2": "セリフなし", "セリフ2": ""}
        for i, (speaker, text) in enumerate(lines, 1):
            kw[f"話者{i}"], kw[f"セリフ{i}"] = speaker, text
        return PH3MangaPanel().build(**kw)[0]

    def test_three_characters_prompt_and_balloons(self):
        img = torch.ones((1, 8, 8, 3))
        panels = [self.panel("人物1のみ", ("人物1", "雨、やまないね。")),
                  self.panel("人物なし", ("画面外・ナレーション（尾なし）", "その日は雨だった。"), scene="A rainy schoolyard."),
                  self.panel("人物1と人物2と人物3", ("人物2", "一緒に帰ろう。"), ("人物1", "うん！"), ("人物3", "いいなぁ"), scene="人物1, 人物2 and 人物3 walk.")]
        page, w, h, prompt, balloons, r1, r2, r3 = PH3MangaPage().build(コマ割り="normal_3_01", 人物1=img, 人物2=img, 人物3=img,
                                                                       コマ1=panels[0], コマ2=panels[1], コマ3=panels[2])
        self.assertEqual((w, h), (1664, 2496))
        self.assertIn("<Picture 4>: attribute_transfer", prompt)
        self.assertIn("the character from <Picture 4> walk", prompt)
        self.assertNotIn("人物", prompt)
        boxes = json.loads(balloons)
        self.assertEqual(len(boxes), 5)
        self.assertIsNone(json.loads(boxes[1]["metadata"]["desc"])["tail"])
        rows = layouts()["normal_3_01"]["panels"]
        for box, panel in zip(boxes, [0, 1, 2, 2, 2]):  # 吹き出しは自分のコマの中
            x0, y0, x1, y1 = rows[panel]["bbox"]
            self.assertGreaterEqual(box["x"], x0 * 1024); self.assertLessEqual(box["x"] + box["width"], x1 * 1024)
            self.assertGreaterEqual(box["y"], y0 * 1536); self.assertLessEqual(box["y"] + box["height"], y1 * 1536)

    def test_left_to_right_order_keeps_headings_and_regions_with_contents(self):
        self.assertEqual(left_to_right_order(layouts()["normal_3_01"]), [0, 1, 2])
        self.assertEqual(left_to_right_order(layouts()["normal_4_05"]), [0, 1, 3, 2])
        img = torch.ones((1, 8, 8, 3))
        panels = [self.panel("人物1のみ", scene=f"SCENE{i} 人物1.") for i in range(1, 5)]
        kw = dict(コマ割り="normal_4_05", 人物1=img, コマ1=panels[0], コマ2=panels[1], コマ3=panels[2], コマ4=panels[3])
        on = PH3MangaPage().build(**kw)[3]
        off = PH3MangaPage().build(**kw, 左から埋める癖を補正=False)[3]
        self.assertTrue(on.startswith("subject_definitions:"))
        self.assertIn("Panel 3 (tier 3, panel 2 from the right): SCENE4", on)
        self.assertIn("Panel 4 (tier 3, panel 1 from the right): SCENE3", on)
        self.assertIn("Panel region 3: left=45, top=670, right=486, bottom=955.", on)
        self.assertIn("Panel region 4: left=514, top=670, right=955, bottom=955.", on)
        self.assertIn("Panel 3 (tier 3, panel 1 from the right): SCENE3", off)

    def test_validation(self):
        img = torch.ones((1, 8, 8, 3))
        with self.assertRaises(ValueError):  # 登場しない人物が話す
            self.panel("人物1のみ", ("人物2", "a"))
        p = self.panel("人物2のみ", ("人物2", "a"))
        with self.assertRaises(ValueError):  # 人物2の画像がない
            PH3MangaPage().build(コマ割り="normal_2_01", 人物1=img, コマ1=p, コマ2=p)
        with self.assertRaises(ValueError):  # コマ数が合わない
            PH3MangaPage().build(コマ割り="normal_3_01", 人物1=img, 人物2=img, コマ1=p, コマ2=p)


if __name__ == "__main__":
    unittest.main()
