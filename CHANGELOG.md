# Changelog

Versions track the user-facing SolarSTATA build. Anything that
moves on-disk state, changes installation behaviour, or
otherwise needs a migration note for existing installs lands
here.

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
