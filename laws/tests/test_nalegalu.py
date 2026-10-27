from pathlib import Path

from django.test import SimpleTestCase

from laws.sources import nalegalu

FIXTURES = Path(__file__).parent / "fixtures" / "nalegalu"


class NalegaluParserTests(SimpleTestCase):
    def setUp(self):
        self.text = nalegalu.load_act(nalegalu.find_act_dir(FIXTURES, "DU/2099/1"))
        self.units = {u.address: u for u, _ in self.text.root.walk()}

    def test_metadata(self):
        act = self.text.act
        self.assertEqual(act.source_id, "DU/2099/1")
        self.assertEqual(act.act_type, "statute")
        self.assertEqual(act.display_address, "Dz.U. 2099 poz. 1")
        self.assertTrue(act.in_force)
        self.assertEqual(self.text.version_date, "2099-03-01")

    def test_structure_and_addresses(self):
        self.assertEqual(self.units["div_I"].heading, "Przepisy ogólne")
        self.assertEqual(self.units["div_I/chp_1"].heading, "Badania techniczne")
        self.assertEqual(self.units["art_1"].text, "Ustawa określa zasady ruchu.")
        self.assertEqual(self.units["art_2/par_2/pt_1"].text, "przed upływem 3 lat od rejestracji;")
        self.assertEqual(self.units["art_2/par_2/pt_2/lit_b"].label, "b)")
        self.assertEqual(self.units["art_3"].text, "(uchylony)")

    def test_articles_hang_under_their_chapter(self):
        chapter = self.units["div_I/chp_1"]
        self.assertEqual([c.address for c in chapter.children], ["art_2", "art_3", "art_4"])

    def test_pdf_wrap_artifact_is_merged_back(self):
        # "... z zastrzeżeniem art." followed by a bare "1." is one sentence, not ust. 1.
        self.assertEqual(self.units["art_2/par_2/pt_2/lit_b"].text, "co rok, z zastrzeżeniem art. 1.")
        self.assertNotIn("art_2/par_1~2", self.units)
