# Mesa Academic League study site

A single-page study tool for the Mesa Academic League quiz-bowl club: all four
quarters of the 2026–27 study guide plus mythology, as eight ways to drill it.
One self-contained HTML file, no libraries, works offline.

**The page is [`index.html`](index.html).**

## Editing the content

Every question, hint and wrong answer lives in a Google Sheet. Editors choose
**Study site → Publish to site** there, which commits
[`content/content.json`](content/content.json); the
[Publish from the sheet](.github/workflows/publish.yml) workflow checks it,
writes it into `mal.html` and rebuilds `index.html`. If something in the sheet
is wrong, nothing is published and the sheet shows which tab and row to fix.

| Path | What it is |
|---|---|
| `index.html` | The built page. Generated — don't edit. |
| `mal.html` | The page source. Its content tables are generated from the sheet; everything else is code. |
| `content/content.json` | The sheet's last publish: one row per line, so the history shows exactly which cells changed. |
| `content/schema.json` | The tabs and columns the sheet is laid out with. |
| `sheet/Code.gs` | The sheet's Apps Script (the Study site menu). |
| `tools/content.py` | Sheet ⇄ page conversion and every validation rule. |
| `tools/interactions.py` | Turns list and matching answer keys into boards. |
| `build.py` | Wraps `mal.html` into `index.html`. |

```bash
python tools/content.py import     # content.json -> mal.html
python tools/scdump.py && python tools/interactions.py --emit && python tools/update_iact.py
python build.py
python tools/test_content.py       # what a publish accepts and refuses
```

### Why rows are never deleted

Students' progress is saved in their own browser, keyed to each question's
position. Deleting a row would shift every later question's progress onto the
wrong question, so a publish that is missing a row is refused. Set **Retired**
to `yes` instead; the question disappears from the site and keeps its place.
