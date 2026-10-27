# LawHub

Laws as code. Every act is versioned in git, tagged down to the paragraph, and
people subscribe to the topics that affect them: "I have a car and live in
Kraków" → notified whenever a change to driving law is proposed or enacted.

Beta scope: Polish driving law, read from the [nalegalu](https://github.com/nalegaluorg/nalegalu)
dataset (CC0), served by a Django web app.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
git clone --depth 1 https://github.com/nalegaluorg/nalegalu ../nalegalu   # ~1.2 GB

python manage.py migrate
python manage.py import_nalegalu --seed pl_driving --nalegalu ../nalegalu
python manage.py createsuperuser
uvicorn config.asgi:application --reload   # site + /mcp
```

Then open http://127.0.0.1:8000: browse acts and topics, sign up, fill in the
questionnaire and see the suggested subscriptions. `/admin/` shows everything.

Run tests with `python manage.py test`.

## Layout

| App | What it owns |
|---|---|
| `laws` | `Jurisdiction`, `Act`, `ActVersion`, `Provision`, `ProvisionText`; the import pipeline (`laws/services.py`), sources (`laws/sources/`), the law git repo writer (`laws/gitstore.py`) and the `import_nalegalu` command |
| `tags` | the topic tree (`Tag`), tags on provisions (`ProvisionTag`), the rule-based tagger and its rules (`tags/rules/pl_driving.yaml`) |
| `accounts` | signup and login, the questionnaire, `Profile` and `Subscription` |

`laws/domain/units.py` is framework-free: every source parses its format into
a tree of `Unit`s with stable addresses, and everything downstream (git,
database, tagger) only sees that tree. A new country means a new source
module, nothing else.

## Data model

- **Provision = stable identity** `(act, address)`, e.g. `(DU/1997/602, "art_81/par_6")`.
  Addresses come from structure (`art_81/par_6/pt_2/lit_a`) and stay the same
  across versions, so tags and subscriptions survive amendments. Chapters are
  not part of article addresses (article numbers are unique within an act);
  `Provision.parent` still follows the document tree so articles inherit
  their chapter's tags.
- **ProvisionText = wording in one ActVersion.** Comparing content hashes
  between versions yields exactly which provisions were added, removed or
  reworded; that drives notifications.
- **Tags are a tree of dotted slugs** (`transport.vehicles.inspection`). A
  parent tag is a category; following it covers everything below. Tags are
  stored where they match and inherited downward when read. Rule tags are
  recomputed on every import, manual and LLM tags are kept.
- **Subscription** targets exactly one tag, act or provision; questionnaire
  suggestions are marked `suggested` and regenerated when it is retaken.

## The law repository

The importer writes a **separate** git repo (`data/law-repo`, configurable via
`LAWHUB_LAW_REPO`):

```
pl/DU/1997/602/
    meta.json     act metadata and version
    text.md       readable text, one provision per line
    units.jsonl   one JSON object per provision (address, label, text, ...)
```

One commit per act version, dated with the version's legal date, so
`git log` is the act's legal history and diffs line up with legal units. Next
step: proposed changes go on branches and become pull requests; merging is
how a change lands.

## Configuration

| Variable | Default |
|---|---|
| `DATABASE_URL` | `sqlite:///data/lawhub.sqlite3` (use Postgres in production) |
| `DJANGO_DEBUG` | `1` |
| `DJANGO_SECRET_KEY` | dev key; required when `DJANGO_DEBUG=0` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `LAWHUB_LAW_REPO` | `data/law-repo` |
| `LAWHUB_NALEGALU` | unset; path to the nalegalu checkout |

## Known limitations (beta)

- nalegalu text is ~99% extracted from PDFs and last updated 2026-07-13.
  Expect artifacts (footnote fragments inside provisions, lost superscripts);
  the parser repairs only the cheap ones (PDF line-wrap fragments).
- Its unified texts mark future wording `<…>` and replaced wording `[…]`
  inline. Affected provisions are flagged `has_pending_change` ("zmiana w
  drodze") but not split into separate versions yet.
- Regex tagging is a first pass and over-tags (art. 81 ust. 6 gets
  `transport.commercial` because it mentions taxis).
- Search is a substring match; on SQLite it is case-sensitive for Polish
  letters. Postgres full-text search with a Polish dictionary is the plan.
- Notifications are not sent yet; `ChangeReport` from the importer is the hook.

## Roadmap

1. Official source: Sejm ELI API (`api.sejm.gov.pl/eli`) using `/struct` for
   official unit ids and `text.html`, PDF fallback; nalegalu becomes a
   fallback. See [prawo-pl-eli](https://github.com/jamarpl21/prawo-pl-eli)
   (MIT) for documented API quirks.
2. Proposals as pull requests: Sejm bills (`api.sejm.gov.pl/sejm`) and
   amending acts open PRs against the law repo; subscribers of affected tags
   are notified on open and on merge.
3. Notifications (email first), Postgres + full-text search.
4. Local law (wojewódzkie dzienniki urzędowe, e.g. Kraków's clean transport
   zone), EU law (EUR-Lex), then other countries.
5. Terraform for hosting.

## Connect your AI (MCP)

Run the site with `uvicorn config.asgi:application`; it serves the MCP
endpoint at `/mcp` next to the website. Logged-in users find setup steps at
`/connect/`. Clients log in with OAuth (authorization code + PKCE via
django-oauth-toolkit, discovered through RFC 9728/8414 metadata, with dynamic
client registration). Tools: `list_topics`, `search_law`, `get_provision`,
`my_subscriptions`, `follow_topics`, `unfollow_topics`, `recent_changes`.
Set `LAWHUB_PUBLIC_URL` to the public https URL in production.

Private beta: `LAWHUB_PRIVATE=1` requires login on every page, and
`LAWHUB_SIGNUP_ALLOWLIST=a@x.com,b@y.com` limits who can sign up.
