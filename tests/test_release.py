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
        self.assertNotRegex(ISS, r"(?i)\{(localappdata|commonappdata)\}")
        # Kun den versionsspecifikke biblioteksmappe ryddes ved opgradering.
        self.assertIn('Type: filesandordirs; Name: "{app}\\_internal"', ISS)

    def test_konfiguration_laegges_kun_hvis_den_mangler(self):
        linjer = [linje for linje in ISS.splitlines()
                  if "{userappdata}" in linje and not linje.startswith(";")]
        self.assertEqual(len(linjer), 1, "kun .env-filen må skrives i %APPDATA%")
        self.assertIn('DestDir: "{userappdata}\\IN-BASE"; DestName: ".env"', linjer[0])
        self.assertIn("onlyifdoesntexist", linjer[0])      # overskriver aldrig
        self.assertIn("uninsneveruninstall", linjer[0])    # slettes ikke ved afinstallation
        self.assertRegex(ISS, r"#ifndef KlientKonfig\s+#error")
        self.assertIn('"/DKlientKonfig=$GenereretKonfig"', SCRIPT)
        # Altid pr. bruger, så {userappdata} er den installerende brugers egen mappe.
        self.assertNotIn("PrivilegesRequiredOverridesAllowed", ISS)

    def test_pakker_hele_pyinstaller_mappen(self):
        self.assertIn('Source: "{#SourceDir}\\*"', ISS)
        self.assertIn("recursesubdirs", ISS)

    def test_central_opdatering_genstarter_og_ser_koerende_app(self):
        from app.infrastructure import opdatering
        from app.ui.enkelt_instans import MUTEX
        self.assertIn(f"AppMutex={MUTEX}", ISS)
        genstart = [linje for linje in ISS.splitlines() if "Check: ErOpdatering" in linje]
        self.assertEqual(len(genstart), 1)
        self.assertNotIn("skipifsilent", genstart[0], "skal også køre ved /VERYSILENT")
        self.assertIn("{param:OPDATERING|0}", ISS)
        kilde = Path(opdatering.__file__).read_text(encoding="utf-8")
        for parameter in ("/VERYSILENT", "/CLOSEAPPLICATIONS", "/OPDATERING=1"):
            self.assertIn(parameter, kilde)


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
        # Udgivelse kun bevidst (-Udgiv) og kun til pilotkanalen via udgiv_version.py.
        self.assertIn("if ($Udgiv)", SCRIPT)
        self.assertIn("udgiv_version.py') udgiv $Installer", SCRIPT)

    def test_script_kraever_ren_arbejdskopi_og_hele_testpakken(self):
        self.assertIn("git -C $Rod status --porcelain", SCRIPT)
        self.assertIn("-m unittest discover -s tests -t .", SCRIPT)
        self.assertIn("$MaksInstaller = 50MB", SCRIPT)

    def test_script_skriver_foelgefil_til_opdateringssiden(self):
        """Indstillinger → Opdateringer læser skemakrav og commit fra <installer>.json."""
        self.assertIn('$infoFil = "$Installer.json"', SCRIPT)
        for felt in ("version = $Version", "kraevet_skema = [int]$Skema", "commit = $Commit",
                     "sha256 = $hash"):
            self.assertIn(felt, SCRIPT)

    def test_spec_udelader_ubrugte_qt_dele(self):
        for del_ in ("qtvirtualkeyboard", "qt6quick", "qt6qml", "qpdf", "opengl32sw"):
            self.assertIn(f"'{del_}'", SPEC)
        self.assertIn("/pyside6/translations/", SPEC)

    def test_frossen_app_skriver_i_brugeromraader(self):
        self.assertTrue(str(stier.KONFIG_FIL).endswith(str(Path("IN-BASE") / ".env")))
        kilde = (ROD / "app" / "infrastructure" / "stier.py").read_text(encoding="utf-8")
        self.assertIn('_LOCALAPPDATA / "IN-BASE" if ER_FROSSET', kilde)

    def test_assets_til_builden_findes(self):
        for navn in ("IN-BASE.ico", "IN-BASE-ikon.svg"):
            self.assertTrue((ROD / "assets" / navn).is_file(), navn)


class KlientKonfigTest(unittest.TestCase):
    """tools/lav_klientkonfig.py: kun URL + offentlig nøgle til installeren."""

    def setUp(self):
        import tempfile
        self.mappe = Path(tempfile.mkdtemp(prefix="inbase-klientkonfig-"))
        self.kilde, self.maal = self.mappe / "kilde.env", self.mappe / "ud" / "IN-BASE.env"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.mappe, ignore_errors=True)

    def _lav(self, indhold):
        import sys
        sys.path.insert(0, str(ROD / "tools"))
        from lav_klientkonfig import lav
        self.kilde.write_text(indhold, encoding="utf-8")
        return lav(self.kilde, self.maal)

    def test_kun_de_to_offentlige_vaerdier_kopieres(self):
        url = self._lav("INBASE_SUPABASE_URL=https://abc.supabase.co\n"
                        "INBASE_SUPABASE_ANON_KEY=sb_publishable_xyz\n"
                        "SUPABASE_TEST_EMAIL=test@x.dk\nSUPABASE_TEST_PASSWORD=hemmelig\n")
        self.assertEqual(url, "https://abc.supabase.co")
        tekst = self.maal.read_text(encoding="utf-8")
        self.assertIn("INBASE_SUPABASE_ANON_KEY=sb_publishable_xyz", tekst)
        self.assertNotIn("hemmelig", tekst)
        self.assertNotIn("TEST", tekst)
        noegler = [l.split("=")[0] for l in tekst.splitlines() if l and not l.startswith("#")]
        self.assertEqual(noegler, ["INBASE_SUPABASE_URL", "INBASE_SUPABASE_ANON_KEY"])

    def test_afviser_secret_noegle_og_manglende_vaerdier(self):
        from app.infrastructure.database.config import KonfigurationsFejl
        for indhold in ("INBASE_SUPABASE_URL=https://abc.supabase.co\n"
                        "INBASE_SUPABASE_ANON_KEY=sb_secret_abc\n",
                        "INBASE_SUPABASE_URL=https://abc.supabase.co\n",
                        "INBASE_SUPABASE_URL=http://localhost:54321\n"
                        "INBASE_SUPABASE_ANON_KEY=sb_publishable_xyz\n"):
            with self.subTest(indhold[:60]), self.assertRaises(KonfigurationsFejl):
                self._lav(indhold)
        self.assertFalse(self.maal.exists())


if __name__ == "__main__":
    unittest.main()
