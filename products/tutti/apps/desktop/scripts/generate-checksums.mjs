#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const targetDir = path.resolve(process.argv[2] ?? "dist");
const ignoredSuffixes = new Set([".blockmap", ".yml"]);

function shouldHash(fileName) {
  return (
    !ignoredSuffixes.has(path.extname(fileName)) &&
    fileName !== "SHA256SUMS.txt"
  );
}

const entries = (await readdir(targetDir, { withFileTypes: true }))
  .filter((entry) => entry.isFile() && shouldHash(entry.name))
  .map((entry) => entry.name)
  .sort();

const lines = [];
for (const entry of entries) {
  const buffer = await readFile(path.join(targetDir, entry));
  const hash = createHash("sha256").update(buffer).digest("hex");
  lines.push(`${hash}  ${entry}`);
}

await writeFile(
  path.join(targetDir, "SHA256SUMS.txt"),
  `${lines.join("\n")}\n`
);
