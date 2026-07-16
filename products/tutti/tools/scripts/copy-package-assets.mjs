import { cp, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const pairs = process.argv.slice(2);

if (pairs.length === 0 || pairs.length % 2 !== 0) {
  console.error(
    "Usage: node tools/scripts/copy-package-assets.mjs <source> <destination> [...]"
  );
  process.exit(1);
}

for (let index = 0; index < pairs.length; index += 2) {
  const source = resolve(pairs[index]);
  const destination = resolve(pairs[index + 1]);

  await mkdir(dirname(destination), { recursive: true });
  await cp(source, destination, { recursive: true });
}
