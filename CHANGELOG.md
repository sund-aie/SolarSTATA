# Changelog

Versions track the user-facing SolarSTATA build. Anything that
moves on-disk state, changes installation behaviour, or
otherwise needs a migration note for existing installs lands
here.

## [3.3.0-a1] – 2026-06-06

### Levene singleton-group accuracy fix

`robvar` (Levene's test) silently dropped any group with fewer
than two observations from the test sample, so the reported W and
p described a different grouping than the one the user asked for —
on the bundled clinic dataset, `plaque_index` by
`education_level` (which has a singleton `unknown` level) reported
W0 = 0.3463 / p = 0.7919 over four groups instead of the correct
W0 = 0.4483 / p = 0.7736 over five. Both scipy and Stata's robvar
include singleton groups (their |x − center| term is 0 but they
count toward k and the between-group term). Only groups with zero
usable observations are excluded now; a singleton's sd renders as
`.` rather than a fabricated value. The engine output on the
bundled dataset now matches `scipy.stats.levene` exactly, with a
regression test pinning the parity.

### Per-category bar colors

Single-group bar charts (and the ungrouped Counts chart) used to
paint every bar the same accent gold, wasting the encoding channel
that grouped bars, box, and scatter already use. Each category bar
now takes its own PALETTE color via the same `_color_for(i)` cycle
— gold first, then info/good/warn shades. The degenerate
no-group single bar stays solid accent: one bar, nothing to cycle.

### Compact letter display on bar charts

Single-group bar charts can now render a compact letter display
(a / b / ab) above the bars as an alternative to significance
brackets, reading the same oneway posthoc comparisons the brackets
already consume — no new statistics. Groups sharing a letter are
not significantly different at strict p < .05 (the bracket alpha).
The letters come from the insert-and-absorb algorithm
(`engine/cld.py`), assigned deterministically so the leftmost
group always reads "a…". A pair whose adjusted p could not be
computed is treated as not significantly different and surfaces an
under-plot caveat (and a widened bottom margin) instead of a
silently invented result. The bar form offers Brackets and Letters
as mutually exclusive toggles.

Sub-grouped (clustered) bars letter every bar too — the journal
convention for two-factor figures: within each sub-group level
(e.g. each timepoint), the group means are compared pairwise with
the same `_pairwise` machinery oneway uses (pooled within-cell
error for that level, Bonferroni/Scheffé/Šidák adjusted) and
lettered independently per level. The bar endpoint computes these
on request (`posthoc_method`), so the clustered form needs no
prior Analyze run; bar positions are exact because the gap
geometry (`bargap`/`bargroupgap`) is pinned in the layout. Bars
whose cell is empty get no letter; a not-computable level surfaces
the shared caveat. Chart overlay ink (letters, bracket stars and
lines) is now remapped to warm cream by the frontend theme layer
in dark mode — previously it rendered near-black on the dark
surface and was effectively invisible.

### Compact letters above box plots

The same letter display extends to grouped box plots — letters
sit just above each box's upper extent, in the identical mono
font as the bracket stars, reading the same posthoc payload. Box
is letters-only: brackets over box-and-whisker are visually
unworkable, so the box form shows just the Letters toggle when a
matching oneway posthoc exists. The box x-axis is now explicitly
category-typed with encounter-order pinning, matching the bars.

### Dead Clean step removed

The wizard advertised a "Clean and recode" step that was a pure
placeholder ("Lands in Phase 3") — a broken promise in the nav.
The wizard is now five steps: Import, Inspect, Analyze, Visualize,
Export, with every step header renumbered ("Step N of 5") and the
left-rail help copy for Analyze / Visualize / Export rewritten to
describe what those steps actually do today instead of promising a
future phase. The clean-and-recode walkthrough entry remains in
the Help panel's catalog as an explicitly deferred item — that is
the honest place for it.

### Plain-language interpretation of results

Every analysis the app runs now explains itself in accurate plain
English. A new rendering layer (`engine/interpret.py`) turns the
result payloads the engine already produces into sentences — one
pure function per result kind (oneway with posthoc pairs, two-way
ANOVA, repeated-measures ANOVA, regression, logit, Shapiro-Wilk,
Levene, tabstat), dispatched uniformly through
`Result.to_response()` as an additive `interpretation` field on
every stats endpoint. Direction always comes from the sign of the
payload's own difference or coefficient with the actual group
names; significance language is strict p < .05 with the shared
p-format ("p < .001" below .001, otherwise two decimals);
non-significant results read "did not differ significantly",
never "equal"; observational results are phrased associationally,
never causally; not-computable values say so rather than invent a
result. The Guided result cards render the sentences as a styled
"Interpretation" block beneath each table, and render nothing at
all when the field is empty.

### Visualize step empty state for all-categorical data

Picking histogram, box, or bar on a dataset with zero numeric-kind
columns previously rendered an empty variable dropdown, a live
bins slider, and a dead Run button — a clear bug that left the
user staring at a form that could not be filled in. The forms now
detect the zero-numerics case and render an explanation instead:
a serif headline ("Your dataset has no continuous variables.")
followed by a sentence that reads the live `columns` array and
names the kinds that ARE present (e.g. "This dataset has 3 binary
and 2 categorical, no measurements"), then points the user to the
Counts chart for the categorical-data case. Scatter and line are
unaffected — they gate on dtype, not kind, so integer-coded
categoricals stay usable on their axes.

### Counts chart for categorical-data frequencies

A new chart type, "Counts" (`POST /api/graphs/counts`), is the
visual counterpart to `tabulate`. The form takes a categorical X,
an optional categorical group, and a `Count` / `Percent` Y-axis
toggle. When percent is selected, a `Normalize percent over`
dropdown picks the scope — `total` (chart sums to 100),
`within_group` (each group sums to 100), or `within_x` (each X
level sums to 100). The default is `total` regardless of grouping
so the math never silently shifts when the user toggles the group
dropdown; an explainer underneath the control signposts that
`within_group` is usually what you want for pre/post comparisons
without switching to it behind the user.

The command preview reads `graph bar (count) y` or `graph bar
(percent) y, over(x)` to match Stata's syntax for the same chart.
The `normalize(...)` suffix is omitted only when the chosen scope
matches Stata's default for the current state — so `percent +
grouped + within_group` shows the bare `over(...)` form (matching
Stata), and `total` or `within_x` append `normalize(...)`. NaN
cells are dropped (`value_counts(dropna=True)`); value labels on
both X and group axes are honoured; encounter order is preserved
via `_groupby_preserve_order` so timepoints like Baseline / 5-day
/ 10-day don't get alphabetised.

## [3.2.0-a1] – 2026-05-24

Part 1 of the v3.2 polish pass — import-format guidance.

### Import-format guide

A "prepare your sheet" panel now sits above the dropzone on the
Import step. Five product-voice rules cover the file-layout
cases that bite users hardest (row 1 = column names, one row per
observation, no merged cells, no title rows above the header,
units in the column name not next to each value), plus a small
good-vs-bad mini-sheet visual showing both layouts side by side.
Always expanded on first visit; user collapse is remembered in
`localStorage["solarstata.format_guide_collapsed"]`.

### Pre-flight header detection

A new `POST /api/data/preflight` route inspects a staged xlsx
upload and returns:

- the detected header row (heuristic finds the first row of
  mostly-text cells followed by a data-like row — fixes the
  canonical TIDY LONG FORMAT case where the header sits on row
  5 under four note/blank rows)
- the row positions above it that will be skipped
- a column-kind summary (numeric / categorical / id / text counts)
- structural issues: merged cells, hidden rows, hidden columns

The HeaderRowPicker fires preflight on mount, defaults its
auto-pick to the detected row instead of always row 1, and
shows a status strip above the row table that reads back what
was found. Wording for the canonical case:

> Header detected on row 5 — rows 1 to 4 look like notes, we
> will skip them.

User clicks on the row table still take precedence — the
auto-pick only flows in when the user hasn't already overridden.

### Error-bar source control on bar and line charts

Bar and line charts now expose an "Error bars" selector with four
options: none, SD, SEM, 95% CI. The chosen indicator labels the
y-axis directly ("mean VHN ± SD" / "± SEM" / "± 95% CI") so the
figure is self-documenting; titles are no longer suffixed with
the indicator. Backward-compat: bar defaults to ci95 (matches
pre-3.2 behaviour); line defaults to none (raw trace, no
aggregation). Switching line to sd / sem / ci95 aggregates by
x-level within each group and renders symmetric error bars.

### Significance brackets on bar charts

Bar charts now overlay significance brackets when the user has
already run a matching oneway with a posthoc correction. The
renderer reads the existing posthoc_block emitted by the engine
(Bonferroni / Scheffé / Sidak — no new statistics computed) and
draws `*` / `**` / `***` over pairs with p_adj < .05 / .01 / .001
(strict inequalities). Brackets are single-factor only: when the
bar form has a sub-group set, the toggle is shown disabled with
"Brackets apply to single-group comparisons." Tukey-HSD is not
yet emitted by the engine and stays on the v3.3 list.

### Brand identity + UI polish

The placeholder typographic logo is replaced with the amber-sun
mark (`#D4B36A` solid disc + 8 radiating pill beams, cardinal and
ordinal) across every brand surface:

- macOS `.icns` (`desktop/build-resources/icon.icns`) and Windows
  `.ico` (`desktop/build-resources/icon.ico`), wired through
  `mac.icon` / `dmg.icon` / `win.icon` in `desktop/package.json`
  so the packaged app no longer ships with the default Electron
  icon.
- Browser tab favicon (`frontend/public/favicon.svg`) referenced
  from `index.html`.
- Topbar wordmark — inline SVG sun mark paired with the
  `solar`*stata* wordmark (italic gold "stata"). The version chip
  reads from `__APP_VERSION__` injected at build time by
  `vite.config.ts` from `frontend/package.json`, shortened to
  `v{major}.{minor}`; it cannot drift out of sync with the actual
  package version again.
- Splash screen (`desktop/src/static/splash.html`) — same
  transparent mark variant, glow effect preserved via CSS
  `drop-shadow`.

The mark exists in two SVG variants under
`desktop/build-resources/`: `icon.svg` (cocoa-tile background for
icon contexts) and `mark.svg` (transparent for the topbar and
splash so it adapts to dark and light themes). `build-icons.py`
regenerates the `.icns` and `.ico` from the master SVG on demand
via cairosvg + Pillow; the rasterized binaries are committed so
production builds never run the rasterizer.

The mode-toggle pill is also centered: the active label sits
inside its highlight rectangle on both Guided and Pro positions
(`flex-1` on the buttons so the two halves of the toggle render
at exactly equal width, matching the pill's fixed 50% calc).

The dark-mode `--good` and `--warn` semantic tokens are retuned
to the exact brand spec values (`#8BB47A` and `#C97A5A`) so the
pre-flight status strip, FormatGuide good/bad tiles, and other
positive/caution surfaces match the brand. Light-mode token
variants remain tuned for their contrast context.

Package versions bumped to `3.2.0-a1` in both
`frontend/package.json` and `desktop/package.json`.

## [3.1.0-a1] – 2026-05-24

v3.1C cleanup pass on top of the v3.1 desktop packaging.

### Log path relocation

The Electron runtime app name is now pinned to `SolarSTATA`
(previously the npm package name `solarstata-desktop` leaked
through to `app.getName()` and seeded every disk path). The
backend log file moves accordingly:

| Platform | Old path | New path |
| --- | --- | --- |
| macOS   | `~/Library/Logs/solarstata-desktop/backend.log` | `~/Library/Logs/SolarSTATA/backend.log` |
| Windows | `%APPDATA%\solarstata-desktop\logs\backend.log` | `%APPDATA%\SolarSTATA\logs\backend.log` |
| Linux   | `~/.config/solarstata-desktop/logs/backend.log` | `~/.config/SolarSTATA/logs/backend.log` |

The old directory is left in place — nothing reads from it but
prior logs aren't deleted automatically. If you want historical
logs in the new location, copy `solarstata-desktop/` →
`SolarSTATA/` once after upgrading; otherwise it's safe to
delete the old folder.

`app.getPath("userData")` and other Electron-derived paths
rebrand consistently. The packaged app's user-facing name
(`SolarSTATA.app`, "SolarSTATA" in the Start menu / Dock) is
unchanged — only the on-disk directory tracks it now.
