// electron-updater reads ONE latest-mac.yml per release, but arm64 and x64 are
// built by separate electron-builder runs (the PyInstaller core freezes only on
// its own architecture), and each run uploads a manifest listing only its own
// files: the last upload wins and the other architecture can no longer update.
//
//   node scripts/merge-manifest.js v0.4.2 arm64   # after that arch's build
//   node scripts/merge-manifest.js v0.4.2         # just re-merge what is there
//
// With an arch, dist/latest-mac.yml is kept on the release as
// latest-mac-<arch>.yml. Then every latest-mac-*.yml on the release is merged
// into latest-mac.yml. Safe to run again at any time. Needs an authenticated gh.
const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const REPO = "austinbyron/towereye";

function merge(manifests) {
  if (!manifests.length) throw new Error("no manifests to merge");
  const versions = [...new Set(manifests.map((m) => m.version))];
  if (versions.length > 1) throw new Error(`version mismatch across manifests: ${versions.join(", ")}`);
  const files = new Map(); // by url: a rebuilt arch replaces its old entry in place
  for (const m of manifests) for (const f of m.files || []) files.set(f.url, f);
  const all = [...files.values()];
  const zip = all.find((f) => f.url.endsWith(".zip")) || all[0];
  return {
    version: versions[0],
    files: all,
    path: zip.url,
    sha512: zip.sha512,
    releaseDate: manifests.map((m) => m.releaseDate).sort().pop(),
  };
}

function gh(...args) {
  return execFileSync("gh", ["release", ...args, "-R", REPO], { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] });
}

function main(tag, arch) {
  const yaml = require("js-yaml");
  if (!tag) throw new Error("usage: merge-manifest.js <tag> [arch]");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "towereye-manifest-"));
  if (arch) {
    const own = path.join(tmp, `latest-mac-${arch}.yml`);
    fs.copyFileSync(path.join(__dirname, "..", "dist", "latest-mac.yml"), own);
    gh("upload", tag, own, "--clobber");
  }
  const parts = path.join(tmp, "parts");
  fs.mkdirSync(parts);
  gh("download", tag, "-p", "latest-mac-*.yml", "-D", parts);
  const names = fs.readdirSync(parts).sort();
  const merged = merge(names.map((n) => yaml.load(fs.readFileSync(path.join(parts, n), "utf8"))));
  const out = path.join(tmp, "latest-mac.yml");
  fs.writeFileSync(out, yaml.dump(merged, { lineWidth: -1 }));
  gh("upload", tag, out, "--clobber");
  console.log(`latest-mac.yml on ${tag}: ${names.join(" + ")} -> ${merged.files.map((f) => f.url).join(", ")}`);
}

module.exports = { merge };

if (require.main === module) {
  try { main(process.argv[2], process.argv[3]); } catch (e) { console.error(String(e.message || e)); process.exit(1); }
}
