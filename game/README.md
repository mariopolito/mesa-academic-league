# Knowledge Engine

An incremental study game built on the study site's questions. It lives at
`/mesa-academic-league/engine/` beside the site, which links to it from a gear
at the end of its tabs. **The site never depends on the game**: the link and a
note of study time are the whole connection.

## Files

| File | What it is |
|---|---|
| `engine_src.html` | The game's source: markup, styles and script, with `/*ITEMS*/[]` where the questions go. |
| `items.json` | The 749 questions, exported from the site (below). |
| `build_game.py` | Writes `engine/index.html` (served), `game/engine.html` (Artifact copy) and `game/Knowledge-Engine.html` (standalone). The last two are local only. |
| `export_items.js`, `export_server.py` | The export. |

Run `python game/build_game.py` after any edit to `engine_src.html`, and commit
`engine/index.html` with it.

## Refreshing the questions after a content change

The site builds its quiz questions in JavaScript when the page loads, so they are
exported from the site rather than rebuilt here. A sheet publish does **not**
refresh the game; until this is re-run, the game asks the old questions.

1. `python build.py` (so `Mesa-Academic-League.html` has the latest content)
2. `python game/export_server.py` (serves the folder on http://127.0.0.1:8765)
3. Open http://127.0.0.1:8765/Mesa-Academic-League.html, make sure all four
   quarters are selected, and run `game/export_items.js` in the console.
   It writes `game/items.json` (749 questions as of September 2026), with the
   flashcard hints matched by card id and answer.
4. `python game/build_game.py`

The tip-offs (`tip`) are not a gear: they are the golden questions, one in
`GOLDEN_ODDS` (50), and they carry the site's `TIPWHY`/`TIPHINTS`.

A new quiz set on the site stops the export until it is given a gear in
`REF` (export_items.js) and `TOPICS` (engine_src.html).

Question ids are the site's (`q70`, `caps/cap:Ohio`, `myth/myth:Zeus~2`), so
progress survives a re-export as long as the site keeps its order.

## Rebuild the Engine (prestige)

Unlocks when all 10 gears are built and the run has earned `REBUILD_GOAL(k)`
sparks (1B, then ×5 each rebuild). Resets sparks, gear levels, tools, pressure
and upgrades except `KEEP_UPS` (shop, trading post). **Mastery is never reset.**
Pays blueprints: `2 × cbrt(run sparks / 1B)` plus one per 10 questions mastered
for the first time ever (`S.masteredEver`, so nothing pays twice). Each blueprint
earned adds `BP_BONUS` (5%) to gear output for good; spending them on `PERKS`
does not remove it.

Pacing measured with a simulated student (8 s an answer, 85% right, buying
everything at once): first rebuild at about 650 answers, then one every
650-1,000 answers. `REBUILD_GOAL` is the knob.

## What the game shares with the site

Both pages are on the same origin, so they share `localStorage`:

- **`mal-q1-room14`** (the site's save) -- the game reads `name` only, and never
  writes to it. When the site has a name, the game uses it; the nameplate
  explains where to change it.
- **`mal-activity`** -- written by the site's study clock, read by the game:
  `{v:1, m:[[startMinute, endMinute], ...]}`, minutes since the epoch, oldest
  first, eight days kept. A minute with a click, key or scroll on a visible
  site page marks itself and the next. While away from the engine, a studied
  minute stops rust and runs the gears at `STUDY.rate` (half speed, no 8-hour
  limit); any other minute rusts and earns `AWAY.rate` (a tenth, 8 hours at most).
- **`mal-engine-v1`** -- the game's own save.

A hidden engine tab counts as time away: the tick stands still while the tab is
hidden and `awayReport()` settles the gap when it comes back, so leaving the game
open in the background earns nothing extra.
