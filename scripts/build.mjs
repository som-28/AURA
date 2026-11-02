import { readdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const root = new URL("../", import.meta.url);
const webDir = new URL("../web/", import.meta.url);
const scripts = (await readdir(webDir)).filter((name) => name.endsWith(".js"));

if (scripts.length === 0) {
  throw new Error("No browser JavaScript files found under web/");
}

for (const script of scripts) {
  const result = spawnSync(process.execPath, ["--check", join(webDir.pathname, script)], {
    cwd: root,
    stdio: "inherit",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const python = spawnSync("python3", ["-m", "compileall", "-q", "src"], {
  cwd: root,
  stdio: "inherit",
});
if (python.status !== 0) process.exit(python.status ?? 1);

console.log(`Build checks passed (${scripts.length} browser scripts and Python sources).`);
