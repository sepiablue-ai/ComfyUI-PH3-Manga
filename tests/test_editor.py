"""統合入力・配布ワークフローを検査する。"""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ph3_editor_tests", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)
from ph3_editor_tests.editor import PAGE_H, PAGE_W, PH3MangaBalloonEditor, PH3MangaScene, PH3MangaStory, lettering_preview, text_elements
from ph3_editor_tests.nodes import PH3MangaLettering
from ph3_editor_tests.page import picture_labels, scene_text
from ph3_editor_tests.editor import needs_translation, translate_scene


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.items = [{"id": "one", "panel": 1, "bbox": [80, 500, 200, 700], "speaker": "人物1", "text": "雨だね。", "tail": [620, 215]}]

    def build(self, items):
        return PH3MangaBalloonEditor().build("normal_2_01", json.dumps(items), .7, 2)

    def test_text_edit_preserves_geometry_and_generation_plan(self):
        first = self.build(self.items)
        edited = copy.deepcopy(self.items)
        edited[0]["text"] = "一緒に帰ろう。\n傘もあるよ。"
        second = self.build(edited)
        self.assertTrue(torch.equal(first[0], second[0]))
        self.assertEqual(first[3], second[3])
        self.assertEqual(first[4][0]["bbox"], second[4][0]["bbox"])
        self.assertNotEqual(first[4][0]["text"], second[4][0]["text"])

    def test_tail_edit_changes_input_guide(self):
        before = self.build(self.items)
        self.items[0]["tail"] = [790, 260]
        after = self.build(self.items)
        self.assertFalse(torch.equal(before[0], after[0]))
        self.assertNotEqual(before[3], after[3])
        self.assertEqual(before[4][0]["bbox"], after[4][0]["bbox"])

    def test_text_region_edit_does_not_modify_guide(self):
        before = self.build(self.items)
        self.items[0]["text_bbox"] = [100, 540, 190, 660]
        after = self.build(self.items)
        self.assertTrue(torch.equal(before[0], after[0]))
        self.assertEqual(before[3], after[3])
        self.assertEqual(after[4][0]["bbox"], self.items[0]["text_bbox"])

    def test_story_uses_editor_speaker_without_passing_text_to_model(self):
        plan = self.build(self.items)[3]
        image = torch.ones((1, 8, 8, 3))
        panel = PH3MangaScene().build("人物1 waves.", "人物1のみ")[0]
        out = PH3MangaStory().build(構成と話者=plan, 人物1=image, コマ1=panel, コマ2=panel)
        self.assertNotIn("雨だね", out[0])
        self.assertIn("(600.0, 140.0)", out[0])
        self.assertIn("belongs to the character from <Picture 2>", out[0])
        bad = json.loads(plan); bad["balloons"][0]["speaker"] = "人物2"
        with self.assertRaises(ValueError):
            PH3MangaStory().build(構成と話者=json.dumps(bad), 人物1=image, コマ1=panel, コマ2=panel)

    def test_invalid_data(self):
        for field, value in [("panel", 3), ("speaker", "人物4"), ("bbox", [0, 0, 0, 20]), ("tail", [-1, 200])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build([{**self.items[0], field: value}])
        with self.assertRaises(ValueError):
            self.build(self.items * 2)


class LetteringPreviewTests(unittest.TestCase):
    """編集画面の見本は、写植ノードと同じ組み方（列・文字サイズ・位置）になる。"""
    def test_preview_matches_lettering_node(self):
        import io
        import numpy as np
        from PIL import Image
        layout = "3コマ・通常03・2／1段組"
        items = [
            {"id": "a", "panel": 1, "bbox": [71.1, 843.4, 279.2, 918.5], "speaker": "人物1", "text": "雨、やまないね。", "tail": [811.5, 233.0]},
            {"id": "b", "panel": 2, "bbox": [260.2, 74.5, 357.1, 167.7], "speaker": "画面外・ナレーション（尾なし）", "text": "うん。\n助かった。", "tail": None,
             "text_bbox": [274.7, 88.4, 342.6, 153.7]},
        ]
        value, ruby = json.dumps(items, ensure_ascii=False), json.dumps({"雨": "あめ"}, ensure_ascii=False)
        *_, texts = PH3MangaBalloonEditor().build(layout, value, 0.7, 2)
        self.assertEqual([t["bbox"] for t in texts], [t["bbox"] for t in text_elements(items, 0.7)])
        page, node_info = PH3MangaLettering().run(torch.ones((1, PAGE_H, PAGE_W, 3)), "auto", "auto", 0.018, texts, ruby)
        png, preview_info = lettering_preview(layout, value, 0.7, "auto", "auto", 0.018, ruby)
        self.assertEqual(preview_info, json.loads(node_info))
        alpha = np.asarray(Image.open(io.BytesIO(png)).getchannel("A"), dtype=np.float32) / 255
        ink = 1 - page[0].mean(-1).numpy()
        self.assertGreater(alpha.sum(), 1000)
        self.assertLess(np.abs(alpha - ink).max(), 0.02)

    def test_preview_rejects_bad_settings(self):
        with self.assertRaises(ValueError):
            lettering_preview("3コマ・通常03・2／1段組", "[]", 0.7, "auto", "auto", 0.018, "not json")
        with self.assertRaises(ValueError):
            lettering_preview("3コマ・通常03・2／1段組", "[]", 2.0, "auto", "auto", 0.018, "{}")


class SceneTextTests(unittest.TestCase):
    def test_character_names_in_japanese_or_english(self):
        labels = picture_labels(["人物1", "人物2"])
        text = scene_text("人物1 waves. 人物２ smiles. Character 1 sits, character2 stands, Person 1 and person-2 talk.", labels)
        self.assertEqual(text, "the character from <Picture 2> waves. the character from <Picture 3> smiles. "
                               "the character from <Picture 2> sits, the character from <Picture 3> stands, "
                               "the character from <Picture 2> and the character from <Picture 3> talk.")
        # 単語の一部や別の番号は置き換えない。
        self.assertEqual(scene_text("Character 12 and MainCharacter 1", labels), "Character 12 and MainCharacter 1")


class TranslationTests(unittest.TestCase):
    class FakeClip:
        def __init__(self, answer):
            self.answer, self.prompts = answer, []
        def tokenize(self, text):
            self.prompts.append(text); return text
        def generate(self, tokens, **kw):
            self.kw = kw; return [1]
        def decode(self, ids):
            return self.answer + "<|im_end|>"

    def test_only_japanese_scenes_are_translated_with_chat_template(self):
        self.assertFalse(needs_translation("人物1 waves at 人物２."))
        self.assertTrue(needs_translation("人物1が手を振る。"))
        clip = self.FakeClip("Character 1 waves.")
        self.assertEqual(translate_scene(clip, "人物1 waves."), "人物1 waves.")
        self.assertEqual(clip.prompts, [])
        self.assertEqual(translate_scene(clip, "人物1が手を振る。"), "Character 1 waves.")
        self.assertTrue(clip.prompts[0].startswith("<|im_start|>user\n") and clip.prompts[0].endswith("<|im_start|>assistant\n"))
        self.assertIn("人物1が手を振る。", clip.prompts[0])
        self.assertFalse(clip.kw["do_sample"])
        self.assertEqual(translate_scene(None, "人物1が手を振る。"), "人物1が手を振る。")

    def test_untranslated_output_is_an_error(self):
        with self.assertRaises(ValueError):
            translate_scene(self.FakeClip("人物1が手を振る。"), "人物1が手を振る。")


class WorkflowTests(unittest.TestCase):
    def assert_connections(self, wf):
        nodes = {n["id"]: n for n in wf["nodes"]}
        links = {link[0]: link for link in wf["links"]}
        self.assertEqual(len(links), len(wf["links"]))
        for n in nodes.values():
            for port, inp in enumerate(n.get("inputs", [])):
                if inp.get("link") is not None:
                    link = links[inp["link"]]
                    self.assertIn(link[1], nodes)
                    self.assertEqual(link[3], n["id"])
                    self.assertEqual(link[4], port)
                    output = nodes[link[1]]["outputs"][link[2]]
                    self.assertIn(link[0], output.get("links") or [])
                    if inp["type"] != "*":
                        self.assertIn(output["type"], inp["type"].split(","))
        return nodes

    def test_generation_uses_single_editor_without_a_saved_image_switch(self):
        wf = json.loads((ROOT / "example_workflows/01_generate_and_letter.json").read_text(encoding="utf-8"))
        nodes = self.assert_connections(wf)
        self.assertEqual(sum(n["type"] == "PH3MangaBalloonEditor" for n in nodes.values()), 1)
        self.assertFalse(any(n["type"] in ("PH3MangaPanel", "CreateBoundingBoxes", "PH3MangaCachedPage") for n in nodes.values()))
        self.assertTrue(any(n["type"] == "SamplerCustomAdvanced" for n in nodes.values()))
        decode = next(n for n in nodes.values() if n["type"] == "VAEDecode")
        targets = [nodes[l[3]]["type"] for l in wf["links"] if l[1] == decode["id"]]
        self.assertCountEqual(targets, ["SaveImage", "PH3MangaLettering"])
        self.assertEqual(nodes[23]["widgets_values"], ["PH3_Manga/raw"])
        shift = next(n for n in nodes.values() if n["type"] == "MiniMaxH3SigmaShift")
        self.assertEqual(shift["widgets_values"], [1.0, 1.0])

    def test_lettering_workflow_has_no_generation_nodes(self):
        wf = json.loads((ROOT / "example_workflows/02_letter_existing_page.json").read_text(encoding="utf-8"))
        nodes = self.assert_connections(wf)
        allowed = {"LoadImage", "GetImageSize", "PrimitiveStringMultiline", "CreateBoundingBoxes", "PH3MangaLettering", "SaveImage", "PreviewAny", "MarkdownNote"}
        self.assertLessEqual({n["type"] for n in nodes.values()}, allowed)
        self.assertEqual(sum(n["type"] == "LoadImage" for n in nodes.values()), 1)
        lettering = next(n for n in nodes.values() if n["type"] == "PH3MangaLettering")
        image_input = next(i for i in lettering["inputs"] if i["name"] == "image")
        source = next(link[1] for link in wf["links"] if link[0] == image_input["link"])
        self.assertEqual(nodes[source]["type"], "LoadImage")


if __name__ == "__main__":
    unittest.main()
