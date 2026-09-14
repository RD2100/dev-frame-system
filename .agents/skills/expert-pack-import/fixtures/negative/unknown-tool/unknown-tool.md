---
name: unknown-tool-checker
description: 演示未识别工具被保留并打印警告的负例夹具。转换器应当成功，但输出目录里的 tools 列表包含小写后的未知名称。
tools: Grep, Foo_Bar99
---

你是负例夹具：这个文件转换成功，但未知工具名称必须原样保留（小写）并出现在警告里。
