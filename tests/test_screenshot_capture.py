"""ScreenshotCapture counting and file numbering, with pyautogui and PIL stubbed (no display needed)."""

import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import tests.helpers  # noqa: F401  (puts src on sys.path)


class FakeImage:
    """Stands in for a PIL image: records where it was saved."""

    def __init__(self):
        self.saved_to = []

    def save(self, path):
        self.saved_to.append(str(path))


class ScreenshotCaptureTest(unittest.TestCase):
    def setUp(self):
        pil = types.ModuleType("PIL")
        pil.Image = types.ModuleType("PIL.Image")
        pil.Image.Image = FakeImage
        self.pyautogui = types.ModuleType("pyautogui")
        self.pyautogui.screenshot = mock.Mock(side_effect=lambda **kwargs: FakeImage())
        stubs = {"PIL": pil, "PIL.Image": pil.Image, "pyautogui": self.pyautogui}
        patcher = mock.patch.dict(sys.modules, stubs)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("playtester.screenshot_capture", None)
        self.module = importlib.import_module("playtester.screenshot_capture")

    def test_counts_captures_without_saving(self):
        capture = self.module.ScreenshotCapture()
        capture.capture_full_screen()
        capture.capture_region(0, 0, 10, 10)
        capture.capture_full_screen()
        self.assertEqual(capture.screenshot_count, 3)

    def test_saved_files_are_numbered_by_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = self.module.ScreenshotCapture(save_screenshots=True, output_dir=tmp)
            first = capture.capture_full_screen()
            second = capture.capture_region(1, 2, 3, 4)
            self.assertEqual(capture.screenshot_count, 2)
            self.assertEqual(first.saved_to, [os.path.join(tmp, "screenshot_0001.png")])
            self.assertEqual(second.saved_to, [os.path.join(tmp, "screenshot_region_0002.png")])
        self.pyautogui.screenshot.assert_called_with(region=(1, 2, 3, 4))


if __name__ == "__main__":
    unittest.main()
