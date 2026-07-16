import {
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  utimesSync,
  writeFileSync
} from "node:fs";
import assert from "node:assert/strict";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { RotatingFileWriter } from "./rotatingFileWriter.ts";

function createTempDir(): string {
  return mkdtempSync(join(tmpdir(), "tutti-desktop-log-test-"));
}

test("RotatingFileWriter rotates the active log when size budget is exceeded", async (t) => {
  const dir = createTempDir();
  t.after(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  const now = new Date(2026, 4, 5, 18, 0, 0, 0);
  const writer = await RotatingFileWriter.create(
    join(dir, "tutti-desktop.log"),
    {
      maxSizeBytes: 5,
      maxBackups: 10,
      maxAgeDays: 14,
      maxTotalBytes: 1024,
      now: () => now
    }
  );

  await writer.write("hello");
  await writer.write("world");
  await writer.close();

  assert.equal(
    readFileSync(join(dir, "tutti-desktop.2026-05-05.log"), "utf8"),
    "hello"
  );
  assert.equal(readFileSync(join(dir, "tutti-desktop.log"), "utf8"), "world");
});

test("RotatingFileWriter rotates on calendar day change", async (t) => {
  const dir = createTempDir();
  t.after(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  let now = new Date(2026, 4, 5, 15, 59, 0, 0);
  const writer = await RotatingFileWriter.create(
    join(dir, "tutti-desktop.log"),
    {
      maxSizeBytes: 1024,
      maxBackups: 10,
      maxAgeDays: 14,
      maxTotalBytes: 2048,
      now: () => now
    }
  );

  await writer.write("before\n");
  now = new Date(2026, 4, 6, 16, 1, 0, 0);
  await writer.write("after\n");
  await writer.close();

  assert.equal(
    readFileSync(join(dir, "tutti-desktop.2026-05-05.log"), "utf8"),
    "before\n"
  );
  assert.equal(readFileSync(join(dir, "tutti-desktop.log"), "utf8"), "after\n");
});

test("RotatingFileWriter prunes older rotated files to stay within directory budget", async (t) => {
  const dir = createTempDir();
  t.after(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  const olderPath = join(dir, "tutti-desktop.2026-05-04.log");
  const newerPath = join(dir, "tutti-desktop.2026-05-05.1.log");
  writeFileSync(olderPath, "older", "utf8");
  writeFileSync(newerPath, "newer", "utf8");

  utimesSync(
    olderPath,
    new Date("2026-05-04T12:00:00.000Z"),
    new Date("2026-05-04T12:00:00.000Z")
  );
  utimesSync(
    newerPath,
    new Date("2026-05-05T12:00:00.000Z"),
    new Date("2026-05-05T12:00:00.000Z")
  );

  const writer = await RotatingFileWriter.create(
    join(dir, "tutti-desktop.log"),
    {
      maxSizeBytes: 1024,
      maxBackups: 10,
      maxAgeDays: 14,
      maxTotalBytes: statSync(olderPath).size + statSync(newerPath).size - 1,
      now: () => new Date(2026, 4, 5, 18, 0, 0, 0)
    }
  );
  await writer.close();

  assert.throws(() => statSync(olderPath));
  assert.equal(readFileSync(newerPath, "utf8"), "newer");
});

test("RotatingFileWriter shared directory budget can prune rotated logs from other components", async (t) => {
  const dir = createTempDir();
  t.after(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  const daemonRotatedPath = join(dir, "tuttid.2026-05-04.log");
  const desktopRotatedPath = join(dir, "tutti-desktop.2026-05-05.1.log");
  writeFileSync(daemonRotatedPath, "daemon-older", "utf8");
  writeFileSync(desktopRotatedPath, "desktop-newer", "utf8");

  utimesSync(
    daemonRotatedPath,
    new Date("2026-05-04T12:00:00.000Z"),
    new Date("2026-05-04T12:00:00.000Z")
  );
  utimesSync(
    desktopRotatedPath,
    new Date("2026-05-05T12:00:00.000Z"),
    new Date("2026-05-05T12:00:00.000Z")
  );

  const writer = await RotatingFileWriter.create(
    join(dir, "tutti-desktop.log"),
    {
      maxSizeBytes: 1024,
      maxBackups: 10,
      maxAgeDays: 14,
      maxTotalBytes:
        statSync(daemonRotatedPath).size +
        statSync(desktopRotatedPath).size -
        1,
      now: () => new Date(2026, 4, 5, 18, 0, 0, 0)
    }
  );
  await writer.close();

  assert.throws(() => statSync(daemonRotatedPath));
  assert.equal(readFileSync(desktopRotatedPath, "utf8"), "desktop-newer");
});
