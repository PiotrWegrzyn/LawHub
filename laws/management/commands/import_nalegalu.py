import tomllib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from laws.services import import_act_text
from laws.sources import nalegalu

SEEDS_DIR = Path(__file__).resolve().parents[2] / "sources" / "seeds"


class Command(BaseCommand):
    help = "Import acts from a local checkout of the nalegalu dataset (github.com/nalegaluorg/nalegalu)."

    def add_arguments(self, parser):
        parser.add_argument("eli", nargs="*", help='ELI ids, e.g. "DU/1997/602"')
        parser.add_argument("--seed", help="import a predefined set, e.g. pl_driving")
        parser.add_argument("--nalegalu", default=settings.LAWHUB_NALEGALU, help="path to the nalegalu checkout")

    def handle(self, *args, **opts):
        if not opts["nalegalu"]:
            raise CommandError("Pass --nalegalu or set LAWHUB_NALEGALU to a nalegalu checkout.")
        root = Path(opts["nalegalu"]).expanduser()
        elis = list(opts["eli"])
        if opts["seed"]:
            seed = SEEDS_DIR / f"{opts['seed']}.toml"
            if not seed.exists():
                raise CommandError(f"Unknown seed {opts['seed']!r}; available: {[p.stem for p in SEEDS_DIR.glob('*.toml')]}")
            elis += [a["eli"] for a in tomllib.loads(seed.read_text(encoding="utf-8"))["acts"]]
        if not elis:
            raise CommandError("Give ELI ids or --seed.")

        for eli in elis:
            try:
                text = nalegalu.load_act(nalegalu.find_act_dir(root, eli))
            except FileNotFoundError as exc:
                self.stderr.write(f"skip {eli}: {exc}")
                continue
            report = import_act_text(text, source=nalegalu.SOURCE_NAME)
            if not report.is_new_version:
                self.stdout.write(f"{eli}: unchanged")
            else:
                delta = f"+{len(report.added)} -{len(report.removed)} ~{len(report.modified)}"
                self.stdout.write(self.style.SUCCESS(f"{eli}: imported @ {report.version.git_commit[:10]} ({delta})"))
