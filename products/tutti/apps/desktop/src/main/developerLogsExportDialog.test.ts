import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDeveloperLogsAgentPrompt,
  createDeveloperLogsExportSuccessDialogOptions,
  handleDeveloperLogsExportSuccessDialogResponse
} from "./developerLogsExportDialog.ts";
import { createTranslator } from "../shared/i18n/index.ts";

test("developer logs export dialog offers copy prompt and open folder actions", () => {
  const options = createDeveloperLogsExportSuccessDialogOptions({
    canceled: false,
    fileCount: 3,
    filePath: "/Users/demo/Downloads/tutti-logs.zip"
  });

  assert.deepEqual(options.buttons, ["Copy Agent Prompt", "Open Folder", "OK"]);
  assert.equal(options.defaultId, 2);
  assert.equal(options.cancelId, 2);
  assert.equal(options.message, "Logs saved");
  assert.equal(
    options.detail.includes("/Users/demo/Downloads/tutti-logs.zip"),
    true
  );
});

test("developer logs export dialog copies an agent prompt for the exported archive", () => {
  let copiedText = "";
  let revealedPath = "";

  handleDeveloperLogsExportSuccessDialogResponse(
    { response: 0 },
    {
      canceled: false,
      fileCount: 2,
      filePath: "/Users/demo/Downloads/tutti-logs.zip"
    },
    {
      showItemInFolder(path) {
        revealedPath = path;
      },
      writeClipboardText(text) {
        copiedText = text;
      }
    }
  );

  assert.equal(revealedPath, "");
  assert.equal(
    copiedText,
    buildDeveloperLogsAgentPrompt({
      filePath: "/Users/demo/Downloads/tutti-logs.zip"
    })
  );
});

test("developer logs agent prompt follows the requested locale", () => {
  const englishPrompt = buildDeveloperLogsAgentPrompt({
    filePath: "/Users/demo/Downloads/tutti-logs.zip",
    translator: createTranslator("en")
  });
  assert.match(englishPrompt, /Log archive: \/Users\/demo\/Downloads/);
  assert.match(englishPrompt, /Please handle it in this order:/);
  assert.doesNotMatch(englishPrompt, /日志压缩包/);

  const chinesePrompt = buildDeveloperLogsAgentPrompt({
    filePath: "/Users/demo/Downloads/tutti-logs.zip",
    translator: createTranslator("zh-CN")
  });
  assert.match(chinesePrompt, /日志压缩包：\/Users\/demo\/Downloads/);
  assert.match(chinesePrompt, /请按下面的顺序处理：/);
  assert.doesNotMatch(chinesePrompt, /Log archive:/);
});

test("developer logs export dialog copies the localized agent prompt", () => {
  let copiedText = "";

  handleDeveloperLogsExportSuccessDialogResponse(
    { response: 0 },
    {
      canceled: false,
      fileCount: 2,
      filePath: "/Users/demo/Downloads/tutti-logs.zip"
    },
    {
      showItemInFolder() {},
      writeClipboardText(text) {
        copiedText = text;
      }
    },
    createTranslator("zh-CN")
  );

  assert.match(copiedText, /日志压缩包：\/Users\/demo\/Downloads/);
  assert.doesNotMatch(copiedText, /Log archive:/);
});

test("developer logs export dialog reveals the exported archive from the open folder action", () => {
  let copiedText = "";
  let revealedPath = "";

  handleDeveloperLogsExportSuccessDialogResponse(
    { response: 1 },
    {
      canceled: false,
      fileCount: 2,
      filePath: "/Users/demo/Downloads/tutti-logs.zip"
    },
    {
      showItemInFolder(path) {
        revealedPath = path;
      },
      writeClipboardText(text) {
        copiedText = text;
      }
    }
  );

  assert.equal(copiedText, "");
  assert.equal(revealedPath, "/Users/demo/Downloads/tutti-logs.zip");
});
