import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const assetsDirectory = new URL("../dist/assets/", import.meta.url);
const files = await readdir(assetsDirectory);
const sizes = await Promise.all(
  files.map(async (file) => ({
    file,
    bytes: (await stat(join(assetsDirectory.pathname, file))).size,
  })),
);

const limits = [
  { pattern: /^AppView-.*\.js$/, bytes: 60_000, label: "AppView" },
  { pattern: /^markdown-.*\.js$/, bytes: 240_000, label: "Markdown runtime" },
  { pattern: /^index-.*\.css$/, bytes: 125_000, label: "Application CSS" },
];

const failures = [];
for (const limit of limits) {
  const asset = sizes.find((item) => limit.pattern.test(item.file));
  if (!asset) {
    failures.push(`${limit.label}: asset not found`);
  } else if (asset.bytes > limit.bytes) {
    failures.push(
      `${limit.label}: ${asset.bytes} bytes exceeds ${limit.bytes} bytes`,
    );
  }
}

if (failures.length) {
  throw new Error(`Bundle budget failed:\n${failures.join("\n")}`);
}
console.log("Bundle budgets passed.");
