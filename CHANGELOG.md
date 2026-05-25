# Changelog

Versions track the user-facing SolarSTATA build. Anything that
moves on-disk state, changes installation behaviour, or
otherwise needs a migration note for existing installs lands
here.

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
