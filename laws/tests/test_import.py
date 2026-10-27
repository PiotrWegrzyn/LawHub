import copy
import tempfile
from pathlib import Path

from django.test import TestCase

from laws.gitstore import GitStore
from laws.models import Act, Provision
from laws.services import import_act_text
from laws.sources import nalegalu
from tags.models import ProvisionTag

FIXTURES = Path(__file__).parent / "fixtures" / "nalegalu"


class ImportTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = GitStore(Path(self.tmp.name) / "law-repo")
        self.text = nalegalu.load_act(nalegalu.find_act_dir(FIXTURES, "DU/2099/1"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_creates_act_provisions_tags_and_commit(self):
        report = import_act_text(self.text, source="nalegalu", store=self.store)
        self.assertTrue(report.is_new_version)
        act = Act.objects.get(source_id="DU/2099/1")
        self.assertEqual(act.repo_path, "pl/DU/2099/1")
        self.assertTrue((self.store.root / "pl/DU/2099/1/units.jsonl").exists())

        par = Provision.objects.get(act=act, address="art_2/par_1")
        self.assertEqual([a.address for a in par.ancestors()], ["art_2/par_1", "art_2", "div_I/chp_1", "div_I", ""])
        direct = set(ProvisionTag.objects.filter(provision=par).values_list("tag__slug", flat=True))
        self.assertIn("transport.vehicles.inspection", direct)
        self.assertIn("transport.vehicles.cars", direct)
        speed = set(ProvisionTag.objects.filter(provision__address="art_4").values_list("tag__slug", flat=True))
        self.assertEqual(speed, {"transport.road.speed", "transport.road.penalties"})

    def test_reimport_is_idempotent(self):
        import_act_text(self.text, source="nalegalu", store=self.store)
        report = import_act_text(self.text, source="nalegalu", store=self.store)
        self.assertFalse(report.is_new_version)
        self.assertEqual(Act.objects.get().versions.count(), 1)

    def test_new_version_reports_changed_provisions(self):
        import_act_text(self.text, source="nalegalu", store=self.store)
        amended = copy.deepcopy(self.text)
        units = {u.address: u for u, _ in amended.root.walk()}
        units["art_4"].text = "Kto przekracza dopuszczalną prędkość, podlega karze grzywny do 5000 zł."
        amended.version_date = "2099-06-01"

        report = import_act_text(amended, source="nalegalu", store=self.store)
        self.assertEqual(report.modified, ["art_4"])
        self.assertEqual(report.added, [])
        act = Act.objects.get()
        self.assertEqual(act.current_version.version_date.isoformat(), "2099-06-01")
        log = self.store._git("log", "--format=%ad", "--date=short").split()
        self.assertEqual(log[:2], ["2099-06-01", "2099-03-01"])
