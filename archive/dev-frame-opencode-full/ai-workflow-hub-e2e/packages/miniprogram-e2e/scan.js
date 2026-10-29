#!/usr/bin/env node
/**
 * 微信小程序E2E测试 — 页面扫描器
 * 自动扫描app.json中所有页面的WXML选择器和JS data字段
 * 输出报告，agent据此编写E2E测试，不需要手动翻文件
 *
 * 用法：node scan.js [项目根目录]
 * 默认：process.cwd()
 */
const fs = require('fs');
const path = require('path');

const projectRoot = process.argv[2] || process.cwd();
const appJsonPath = path.join(projectRoot, 'app.json');

if (!fs.existsSync(appJsonPath)) {
  console.error('❌ 找不到 app.json，请确认项目路径');
  process.exit(1);
}

const appJson = JSON.parse(fs.readFileSync(appJsonPath, 'utf8'));
const pages = appJson.pages || [];

// 检测miniprogram子目录
const hasMiniprogramDir = fs.existsSync(path.join(projectRoot, 'miniprogram'));
const mpRoot = hasMiniprogramDir ? path.join(projectRoot, 'miniprogram') : projectRoot;

console.log(`\n🔍 扫描项目: ${projectRoot}`);
console.log(`📁 小程序根目录: ${mpRoot}`);
console.log(`📄 共 ${pages.length} 个页面\n`);

const results = [];

for (const pagePath of pages) {
  const pageDir = path.join(mpRoot, pagePath);
  const pageName = path.basename(pagePath);
  const info = { pagePath, pageName, selectors: {}, dataFields: {}, methods: [] };

  // 扫描WXML
  const wxmlPath = path.join(pageDir, `${pageName}.wxml`);
  if (fs.existsSync(wxmlPath)) {
    const wxml = fs.readFileSync(wxmlPath, 'utf8');
    info.selectors = extractSelectors(wxml);
  } else {
    info.selectors._error = 'WXML文件不存在';
  }

  // 扫描JS
  const jsPath = path.join(pageDir, `${pageName}.js`);
  if (fs.existsSync(jsPath)) {
    const js = fs.readFileSync(jsPath, 'utf8');
    info.dataFields = extractDataFields(js);
    info.methods = extractMethods(js);
  } else {
    info.dataFields._error = 'JS文件不存在';
  }

  results.push(info);
}

// 输出报告
console.log('='.repeat(60));
for (const info of results) {
  console.log(`\n## ${info.pagePath}`);
  console.log(`   页面名: ${info.pageName}`);

  if (Object.keys(info.selectors).length > 0) {
    console.log(`   选择器:`);
    for (const [key, value] of Object.entries(info.selectors)) {
      console.log(`     ${key}: ${value}`);
    }
  }

  if (Object.keys(info.dataFields).length > 0) {
    console.log(`   Data字段:`);
    for (const [key, value] of Object.entries(info.dataFields)) {
      console.log(`     ${key}: ${value}`);
    }
  }

  if (info.methods.length > 0) {
    console.log(`   方法: ${info.methods.join(', ')}`);
  }
}
console.log('\n' + '='.repeat(60));

// 生成JSON报告供程序使用
const reportPath = path.join(projectRoot, 'tests', 'e2e', 'scan-report.json');
const reportDir = path.dirname(reportPath);
if (!fs.existsSync(reportDir)) fs.mkdirSync(reportDir, { recursive: true });
fs.writeFileSync(reportPath, JSON.stringify(results, null, 2), 'utf8');
console.log(`\n✅ 扫描报告已保存: ${reportPath}`);

// ========== 工具函数 ==========

function extractSelectors(wxml) {
  const selectors = {};
  // 提取class="xxx"
  const classRegex = /class="([^"]+)"/g;
  let match;
  const classSet = new Set();
  while ((match = classRegex.exec(wxml)) !== null) {
    const classes = match[1].trim().split(/\s+/);
    for (const cls of classes) {
      if (cls && !cls.startsWith('weui')) { // 过滤weui内置样式
        classSet.add(cls);
      }
    }
  }
  if (classSet.size > 0) {
    selectors.classes = Array.from(classSet).map(c => `.${c}`).join(', ');
  }

  // 提取bindtap="xxx" 事件绑定
  const tapRegex = /bindtap="([^"]+)"/g;
  const taps = [];
  while ((match = tapRegex.exec(wxml)) !== null) {
    taps.push(match[1]);
  }
  if (taps.length > 0) {
    selectors.tapEvents = taps.join(', ');
  }

  // 提取data-xxx属性
  const dataAttrRegex = /data-(\w+)=/g;
  const dataAttrs = new Set();
  while ((match = dataAttrRegex.exec(wxml)) !== null) {
    dataAttrs.add(match[1]);
  }
  if (dataAttrs.size > 0) {
    selectors.dataAttributes = Array.from(dataAttrs).join(', ');
  }

  return selectors;
}

function extractDataFields(js) {
  const fields = {};
  // 匹配 data: { ... } 中的字段
  const dataMatch = js.match(/data\s*:\s*\{([\s\S]*?)\n\s*\}/);
  if (dataMatch) {
    const dataBlock = dataMatch[1];
    const fieldRegex = /^\s*(\w+)\s*:\s*(.*?),?\s*$/gm;
    let fieldMatch;
    while ((fieldMatch = fieldRegex.exec(dataBlock)) !== null) {
      const name = fieldMatch[1];
      let value = fieldMatch[2].trim().replace(/,$/, '');
      // 简化显示
      if (value.length > 50) value = value.substring(0, 50) + '...';
      fields[name] = value;
    }
  }
  return fields;
}

function extractMethods(js) {
  const methods = [];
  // 匹配页面方法名
  const methodRegex = /(?:async\s+)?(\w+)\s*\(/g;
  const skip = new Set([
    'require', 'module', 'exports', 'Page', 'App', 'getApp',
    'if', 'else', 'for', 'while', 'switch', 'case', 'return',
    'function', 'const', 'let', 'var', 'new', 'this', 'true', 'false',
    'null', 'undefined', 'typeof', 'instanceof', 'try', 'catch',
    'console', 'wx', 'setData', 'getData', 'onLoad', 'onShow',
    'onReady', 'onHide', 'onUnload', 'onPullDownRefresh',
    'onReachBottom', 'onShareAppMessage',
  ]);

  // 只匹配顶层方法
  const pageMatch = js.match(/Page\s*\(\s*\{([\s\S]*)\}\s*\)/);
  if (pageMatch) {
    const pageBlock = pageMatch[1];
    const topMethodRegex = /^\s*(\w+)\s*\(/gm;
    let m;
    while ((m = topMethodRegex.exec(pageBlock)) !== null) {
      const name = m[1];
      if (!skip.has(name) && !name.startsWith('_') && !methods.includes(name)) {
        methods.push(name);
      }
    }
  }

  return methods;
}
