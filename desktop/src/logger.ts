/* Backend log file management.
 *
 * Pipes uvicorn stdout/stderr into a rolling log file at the
 * platform-conventional location:
 *   macOS:   ~/Library/Logs/SolarSTATA/backend.log
 *   Windows: %APPDATA%\SolarSTATA\Logs\backend.log
 *   Linux:   ~/.config/SolarSTATA/logs/backend.log
 *
 * `app.getPath('logs')` resolves to the right OS path automatically
 * (Electron handles the cross-platform mapping). We create the file
 * fresh on each launch and keep the previous run as backend.log.1.
 */

import { app } from "electron";
import * as fs from "fs";
import * as path from "path";

let stream: fs.WriteStream | null = null;

export function openLog(): { logPath: string; stream: fs.WriteStream } {
  const logsDir = app.getPath("logs");
  if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
  }
  const logPath = path.join(logsDir, "backend.log");
  const prevPath = path.join(logsDir, "backend.log.1");
  if (fs.existsSync(logPath)) {
    try {
      fs.renameSync(logPath, prevPath);
    } catch {
      // best-effort rotation — non-fatal
    }
  }
  stream = fs.createWriteStream(logPath, { flags: "a" });
  stream.write(`\n=== SolarSTATA backend log opened ${new Date().toISOString()} ===\n`);
  return { logPath, stream };
}

export function logLine(line: string): void {
  if (stream) stream.write(line.endsWith("\n") ? line : line + "\n");
  if (process.env.SOLARSTATA_DEV) {
    process.stdout.write("[backend] " + line + (line.endsWith("\n") ? "" : "\n"));
  }
}

export function closeLog(): void {
  if (stream) {
    stream.end(`=== closed ${new Date().toISOString()} ===\n`);
    stream = null;
  }
}
