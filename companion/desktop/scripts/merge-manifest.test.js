const test = require("node:test");
const assert = require("node:assert");
const { merge } = require("./merge-manifest");

function manifest(arch, version = "0.4.2", releaseDate = "2026-09-20T00:00:00.000Z") {
  return {
    version,
    files: [
      { url: `towereye-mac-${arch}.zip`, sha512: `zip-${arch}`, size: 1 },
      { url: `towereye-mac-${arch}.dmg`, sha512: `dmg-${arch}`, size: 2 },
    ],
    path: `towereye-mac-${arch}.zip`,
    sha512: `zip-${arch}`,
    releaseDate,
  };
}

test("a single arch passes through unchanged", () => {
  assert.deepStrictEqual(merge([manifest("arm64")]), manifest("arm64"));
});

test("two arches list every file, in either order", () => {
  for (const order of [["arm64", "x64"], ["x64", "arm64"]]) {
    const urls = merge(order.map((a) => manifest(a))).files.map((f) => f.url).sort();
    assert.deepStrictEqual(urls, [
      "towereye-mac-arm64.dmg", "towereye-mac-arm64.zip",
      "towereye-mac-x64.dmg", "towereye-mac-x64.zip",
    ]);
  }
});

test("path and sha512 point at a listed zip", () => {
  const out = merge([manifest("arm64"), manifest("x64")]);
  const zip = out.files.find((f) => f.url === out.path);
  assert.ok(zip && zip.url.endsWith(".zip"));
  assert.strictEqual(out.sha512, zip.sha512);
});

test("merging an already merged manifest changes nothing", () => {
  const once = merge([manifest("arm64"), manifest("x64")]);
  assert.deepStrictEqual(merge([once, manifest("x64"), manifest("arm64")]), once);
});

test("a rebuilt arch replaces its old entry", () => {
  const rebuilt = manifest("x64");
  rebuilt.files[0].sha512 = "zip-x64-v2";
  const out = merge([manifest("arm64"), manifest("x64"), rebuilt]);
  assert.strictEqual(out.files.find((f) => f.url === "towereye-mac-x64.zip").sha512, "zip-x64-v2");
  assert.strictEqual(out.files.length, 4);
});

test("the newest release date wins", () => {
  const out = merge([manifest("arm64", "0.4.2", "2026-09-20T05:00:00.000Z"), manifest("x64")]);
  assert.strictEqual(out.releaseDate, "2026-09-20T05:00:00.000Z");
});

test("mismatched versions refuse to merge", () => {
  assert.throws(() => merge([manifest("arm64", "0.4.2"), manifest("x64", "0.4.1")]), /version/);
});

test("nothing to merge is an error", () => {
  assert.throws(() => merge([]), /no manifests/);
});
