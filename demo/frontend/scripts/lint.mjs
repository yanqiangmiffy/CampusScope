// oxlint skips files that git ignores, and the repository ignores paper/: pass the sources explicitly
import { spawnSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const files = [];
const walk = d => {
  for (const f of readdirSync(d)) {
    const p = join(d, f);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(p)) files.push(p);
  }
};
walk("src");
const bin = join("node_modules", ".bin", process.platform === "win32" ? "oxlint.cmd" : "oxlint");
const r = spawnSync(bin, ["--deny-warnings", ...files], { stdio: "inherit", shell: process.platform === "win32" });
process.exit(r.status ?? 1);
