/**
 * 微信小程序E2E测试 — 连接验证（通用，无需修改）
 * 每个项目的第一个E2E测试，验证DevTools连接是否正常
 */
const { connect } = require('./helpers');
const config = require('./config');

describe('DevTools连接验证', () => {
  let miniProgram;

  beforeAll(async () => {
    miniProgram = await connect(config.automatorPort);
  }, 30000);

  afterAll(async () => {
    if (miniProgram) await miniProgram.disconnect();
  });

  test('应成功连接到DevTools', () => {
    expect(miniProgram).toBeTruthy();
  });

  test('应能reLaunch到首页', async () => {
    const pages = require('./../../../app.json').pages;
    const homePath = pages[0];
    const page = await miniProgram.reLaunch(homePath);
    await page.waitFor(2000);
    expect(page).toBeTruthy();
  });

  test('应能读取页面data', async () => {
    const pages = require('./../../../app.json').pages;
    const homePath = pages[0];
    const page = await miniProgram.reLaunch(homePath);
    await page.waitFor(2000);
    const data = await page.data();
    expect(data).toBeDefined();
  });
});
