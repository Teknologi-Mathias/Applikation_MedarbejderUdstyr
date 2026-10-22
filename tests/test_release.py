"""Release-processen: én versionskilde og sammenhæng mellem spec, installer og script."""
import re
import unittest
from pathlib import Path

import app
from app.infrastructure import stier

ROD = Path(__file__).resolve().parents[1]
SPEC = (ROD / "MedarbejderUdstyr.spec").read_text(encoding="utf-8")
ISS = (ROD / "installer" / "IN-BASE.iss").read_text(encoding="utf-8-sig")
SCRIPT = (ROD / "scripts" / "build_windows.ps1").read_text(encoding="utf-8-sig")
APP_ID = "C5BFD02A-D4D8-418F-8093-BC7609B78B60"   # må aldrig ændres


class VersionTest(unittest.TestCase):
    def test_version_er_semantisk_og_visning_afledes(self):
        self.assertRegex(app.__version__, r"^\d+\.\d+\.\d+$")
        self.assertEqual(app.VERSION, f"V{app.__version__}")
        self.assertEqual(app.version_tupel("1.10.3"), (1, 10, 3))
        for ugyldig in ("V1.0.0", "1.0", "1.0.0-beta", "", "1.0.0.0"):
            with self.subTest(ugyldig), self.assertRaises(ValueError):
                app.version_tupel(ugyldig)

    def test_versionen_skrives_kun_et_sted(self):
        """Ingen hårdkodede versionsnumre i spec, installer eller buildscript."""
        for navn, tekst in (("spec", SPEC), ("iss", ISS), ("ps1", SCRIPT)):
            with self.subTest(navn):
                self.assertNotIn(app.__version__, tekst)
        self.assertIn("version_tupel()", SPEC)
        self.assertIn("ProductVersion\", __version__", SPEC)
        self.assertIn("app.__version__", SCRIPT)
        self.assertIn('"/DAppVersion=$Version"', SCRIPT)


class InstallerTest(unittest.TestCase):
    def test_version_bruges_i_metadata_og_filnavn(self):
        self.assertIn("AppVersion={#AppVersion}", ISS)
        self.assertIn("VersionInfoVersion={#AppVersion}", ISS)
        self.assertIn("OutputBaseFilename=IN-BASE-Setup-v{#AppVersion}", ISS)
        self.assertIn('$InstallerNavn = "IN-BASE-Setup-v$Version.exe"', SCRIPT)
        self.assertRegex(ISS, r'#ifndef AppVersion\s+#error')

    def test_stabilt_appid_og_ingen_administratorkrav(self):
        self.assertIn(f"AppId={{{{{APP_ID}}}", ISS)
        self.assertIn("PrivilegesRequired=lowest", ISS)

    def test_brugerdata_roeres_ikke(self):
        self.assertNotRegex(ISS, r"(?m)^\[UninstallDelete\]")
        self.assertNotRegex(ISS, r"(?i)\{(userappdata|localappdata|commonappdata)\}")
        # Kun den versionsspecifikke biblioteksmappe ryddes ved opgradering.
        self.assertIn('Type: filesandordirs; Name: "{app}\\_internal"', ISS)

    def test_pakker_hele_pyinstaller_mappen(self):
        self.assertIn('Source: "{#SourceDir}\\*"', ISS)
        self.assertIn("recursesubdirs", ISS)


class BuildTest(unittest.TestCase):
    def test_spec_pakker_kun_assets_og_ingen_hemmeligheder(self):
        datas = re.search(r"datas=(.*)", SPEC).group(1)
        self.assertIn("('assets', 'assets')", datas)
        self.assertIn("collect_data_files('certifi')", datas)
        self.assertNotRegex(datas, r"\.env|Data|Lokal|\.git")
        for pakke in ("supabase", "supabase_auth", "supabase_functions", "postgrest"):
            self.assertIn(f'"{pakke}"', SPEC)

    def test_script_sletter_ikke_release_og_publicerer_ikke(self):
        self.assertNotRegex(SCRIPT, r"Remove-Item[^\n]*ReleaseMappe")
        self.assertNotRegex(SCRIPT, r"(?i)\bgit\s+(commit|push|tag)|gh\s+release")

    def test_frossen_app_skriver_i_brugeromraader(self):
        self.assertTrue(str(stier.KONFIG_FIL).endswith(str(Path("IN-BASE") / ".env")))
        kilde = (ROD / "app" / "infrastructure" / "stier.py").read_text(encoding="utf-8")
        self.assertIn('_LOCALAPPDATA / "IN-BASE" if ER_FROSSET', kilde)

    def test_assets_til_builden_findes(self):
        for navn in ("IN-BASE.ico", "IN-BASE-ikon.svg"):
            self.assertTrue((ROD / "assets" / navn).is_file(), navn)


if __name__ == "__main__":
    unittest.main()
