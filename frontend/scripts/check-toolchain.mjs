import { readFileSync } from "node:fs";

const manifest = JSON.parse(readFileSync("package.json", "utf8"));
const lockfile = JSON.parse(readFileSync("package-lock.json", "utf8"));

const baseline = {
  "@vitejs/plugin-vue": 6,
  vite: 8,
  vitest: 4,
  "vue-tsc": 3,
};

function major(version) {
  const match = String(version).match(/\d+/);
  if (!match) throw new Error(`Cannot parse version: ${version}`);
  return Number(match[0]);
}

const root = lockfile.packages?.[""];
if (!root || lockfile.lockfileVersion !== 3) {
  throw new Error("package-lock.json must use npm lockfileVersion 3");
}

for (const [name, minimumMajor] of Object.entries(baseline)) {
  const declared = manifest.devDependencies?.[name];
  const lockedDeclaration = root.devDependencies?.[name];
  const resolved = lockfile.packages?.[`node_modules/${name}`]?.version;
  if (!declared || !lockedDeclaration || !resolved) {
    throw new Error(`${name} must be declared and resolved in package-lock.json`);
  }
  if (declared !== lockedDeclaration) {
    throw new Error(
      `${name} declaration differs between package.json and package-lock.json`,
    );
  }
  if (major(declared) < minimumMajor || major(resolved) < minimumMajor) {
    throw new Error(
      `${name} must remain on major ${minimumMajor}+; `
        + `declared=${declared}, resolved=${resolved}`,
    );
  }
  process.stdout.write(`${name}: ${resolved}\n`);
}

if (manifest.engines?.node !== ">=20.19.0") {
  throw new Error("frontend Node baseline must remain >=20.19.0");
}

process.stdout.write("Frontend toolchain baseline passed.\n");
