"""Regression coverage for local-first UI design assets."""

from __future__ import annotations

from pathlib import Path
import unittest

from ui.theme import (
    LOCAL_DESIGN_ASSET_CSS,
    MATERIAL_ICONS_PATH,
    PLUS_JAKARTA_400_PATH,
    PLUS_JAKARTA_500_PATH,
    PLUS_JAKARTA_600_PATH,
    PLUS_JAKARTA_700_PATH,
    PLUS_JAKARTA_800_PATH,
)


class LocalDesignAssetTests(unittest.TestCase):
    def test_required_font_assets_are_self_hosted(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        for asset_path in [
            PLUS_JAKARTA_400_PATH,
            PLUS_JAKARTA_500_PATH,
            PLUS_JAKARTA_600_PATH,
            PLUS_JAKARTA_700_PATH,
            PLUS_JAKARTA_800_PATH,
            MATERIAL_ICONS_PATH,
        ]:
            with self.subTest(asset_path=asset_path):
                file_path = (
                    repo_root / "ui" / "assets" / asset_path.removeprefix("/assets/")
                )
                self.assertTrue(file_path.exists())
                self.assertGreater(file_path.stat().st_size, 0)

    def test_design_asset_css_uses_local_urls(self) -> None:
        self.assertIn("@font-face", LOCAL_DESIGN_ASSET_CSS)
        self.assertIn("font-family: 'Plus Jakarta Sans'", LOCAL_DESIGN_ASSET_CSS)
        self.assertIn("font-family: 'Material Icons'", LOCAL_DESIGN_ASSET_CSS)
        self.assertIn("/assets/fonts/plus-jakarta-sans-400.ttf", LOCAL_DESIGN_ASSET_CSS)
        self.assertIn("/assets/fonts/material-icons-regular.ttf", LOCAL_DESIGN_ASSET_CSS)
        self.assertNotIn("fonts.googleapis.com", LOCAL_DESIGN_ASSET_CSS)
        self.assertNotIn("fonts.gstatic.com", LOCAL_DESIGN_ASSET_CSS)

    def test_ui_design_files_do_not_reference_google_font_hosts(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        for relative_path in [
            "app.py",
            "ui/theme.py",
            "ui/routes/dashboard.py",
            "ui/components/dashboard_shell.py",
        ]:
            with self.subTest(relative_path=relative_path):
                content = (repo_root / relative_path).read_text()
                self.assertNotIn("fonts.googleapis.com", content)
                self.assertNotIn("fonts.gstatic.com", content)
                self.assertNotIn("Material+Icons", content)
