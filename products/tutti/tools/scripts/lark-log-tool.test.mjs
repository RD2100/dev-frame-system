import assert from "node:assert/strict";
import test from "node:test";

import {
  applyBugRecordDefaults,
  messageToFileCandidate,
  parseFeishuRecordLink,
  parseLogLine,
  parseMessageFileContent,
  selectRecordAttachment,
  summarizeLogLines
} from "./lark-log-tool.mjs";

test("parseMessageFileContent extracts Feishu message file metadata", () => {
  assert.deepEqual(
    parseMessageFileContent(
      '<file key="file_v3_0012c_ac25e4a4-d2aa-4930-838d-4e5d763f198g" name="tutti-logs-20260605-201724.zip"/>'
    ),
    {
      key: "file_v3_0012c_ac25e4a4-d2aa-4930-838d-4e5d763f198g",
      name: "tutti-logs-20260605-201724.zip"
    }
  );
});

test("messageToFileCandidate normalizes lark-cli message search results", () => {
  assert.deepEqual(
    messageToFileCandidate({
      chat_name: "Nexight业务群",
      content: '<file key="file_v3_001" name="diagnostics &amp; traces.zip"/>',
      create_time: "2026-06-05 20:17",
      message_id: "om_x100",
      sender: {
        name: "Alita"
      }
    }),
    {
      chatName: "Nexight业务群",
      createTime: "2026-06-05 20:17",
      file: {
        key: "file_v3_001",
        name: "diagnostics & traces.zip"
      },
      messageId: "om_x100",
      resourceType: "messageResource",
      senderName: "Alita"
    }
  );
});

test("parseFeishuRecordLink extracts record links and optional Base identifiers", () => {
  assert.deepEqual(
    parseFeishuRecordLink(
      "https://ccn53rwonxso.feishu.cn/record/SHxIrAIRie2Jaeck6zZce97vn3f"
    ),
    {
      baseToken: "",
      recordId: "SHxIrAIRie2Jaeck6zZce97vn3f",
      tableId: ""
    }
  );

  assert.deepEqual(
    parseFeishuRecordLink(
      "https://example.feishu.cn/base/app123/table/tbl456?record_id=rec789"
    ),
    {
      baseToken: "app123",
      recordId: "rec789",
      tableId: "tbl456"
    }
  );
});

test("parseFeishuBaseLink extracts base table and view identifiers", async () => {
  const { parseFeishuBaseLink } = await import("./lark-log-tool.mjs");
  assert.deepEqual(
    parseFeishuBaseLink(
      "https://example.feishu.cn/base/app123?table=tbl456&view=vew789"
    ),
    {
      baseToken: "app123",
      tableId: "tbl456",
      viewId: "vew789"
    }
  );
});

test("selectRecordAttachment prefers zip-like log attachments", () => {
  assert.deepEqual(
    selectRecordAttachment({
      Screen: [{ file_token: "tok_png", name: "screenshot.png" }],
      日志: [
        { file_token: "tok_txt", name: "tutti.log" },
        { file_token: "tok_zip", name: "tutti-logs.zip" }
      ]
    }),
    {
      fieldName: "日志",
      name: "tutti-logs.zip",
      token: "tok_zip"
    }
  );
});

test("applyBugRecordDefaults fills one-click Base record settings", () => {
  assert.deepEqual(
    applyBugRecordDefaults(
      {
        issue: "cannot reply",
        recordUrl: "https://example.feishu.cn/record/rec123"
      },
      {
        bugRecord: {
          attachmentField: "日志",
          baseToken: "app123",
          recordTimeField: "反馈时间",
          tableId: "tbl456",
          viewId: "vew789"
        }
      }
    ),
    {
      attachmentField: "日志",
      baseToken: "app123",
      issue: "cannot reply",
      recordTimeField: "反馈时间",
      recordUrl: "https://example.feishu.cn/record/rec123",
      tableId: "tbl456",
      viewId: "vew789"
    }
  );
});

test("parseLogLine extracts structured log fields", () => {
  assert.deepEqual(
    parseLogLine(
      'time=2026-06-05T12:16:34.148Z level=error component="tutti-desktop" msg="renderer diagnostic" renderer_details={"message":"interactive request is no longer live","name":"TuttidProtocolError"} renderer_event="renderer.unhandled_rejection"'
    ),
    {
      component: "tutti-desktop",
      detailError: null,
      level: "error",
      message: "renderer diagnostic",
      rendererMessage: "interactive request is no longer live",
      stderrMessage: null,
      time: "2026-06-05T12:16:34.148Z"
    }
  );
});

test("summarizeLogLines groups levels, messages, and detail errors", () => {
  const summary = summarizeLogLines([
    'time=2026-06-05T09:02:08.823Z level=warn component="tutti-desktop" msg="terminal diagnostic" details={"error":"Tuttid event stream catalog revision mismatch."}',
    'time=2026-06-05T12:16:34.148Z level=error component="tutti-desktop" msg="renderer diagnostic" renderer_details={"message":"interactive request is no longer live"}',
    'time=2026-06-05T12:16:37.680+08:00 level=INFO msg="agent session ACP stdout" component=tuttid'
  ]);

  assert.equal(summary.levels.get("warn"), 1);
  assert.equal(summary.levels.get("error"), 1);
  assert.equal(summary.levels.get("info"), 1);
  assert.equal(summary.messageCounts.get("terminal diagnostic"), 1);
  assert.equal(
    summary.detailErrorCounts.get(
      "Tuttid event stream catalog revision mismatch."
    ),
    1
  );
  assert.equal(summary.latestImportant.length, 2);
});
