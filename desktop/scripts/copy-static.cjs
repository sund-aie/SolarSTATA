/* Copy non-TS assets (splash HTML, etc.) into build/ so the
 * compiled main.js can resolve them next to itself.
 */

const fs = require("fs");
const path = require("path");

const srcDir = path.join(__dirname, "..", "src", "static");
const dstDir = path.join(__dirname, "..", "build", "static");

if (!fs.existsSync(srcDir)) {
  console.log("(no static dir to copy)");
  process.exit(0);
}

fs.mkdirSync(dstDir, { recursive: true });
for (const entry of fs.readdirSync(srcDir)) {
  const from = path.join(srcDir, entry);
  const to = path.join(dstDir, entry);
  fs.copyFileSync(from, to);
  console.log(`copied ${entry}`);
}
