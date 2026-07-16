import assert from "node:assert/strict";
import test from "node:test";
import { formatIssueManagerTopicSelectorTriggerLabel } from "./IssueManagerTopicSelector.tsx";

test("topic selector prefixes active topic titles with localized topic labels", () => {
  assert.equal(
    formatIssueManagerTopicSelectorTriggerLabel({
      title: "work",
      topicLabel: "Topic"
    }),
    "Topic-work"
  );
  assert.equal(
    formatIssueManagerTopicSelectorTriggerLabel({
      title: "工作",
      topicLabel: "主题"
    }),
    "主题-工作"
  );
});

test("topic selector uses the topic label placeholder without an active title", () => {
  assert.equal(
    formatIssueManagerTopicSelectorTriggerLabel({
      title: "",
      topicLabel: "Topic"
    }),
    "Topic"
  );
});
