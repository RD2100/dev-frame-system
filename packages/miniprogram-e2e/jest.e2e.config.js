/**
 * 微信小程序E2E测试 — 通用Jest配置
 * 各项目复制到 tests/e2e/jest.e2e.config.js 即可，无需修改
 */
module.exports = {
  testMatch: ['**/*.e2e.js'],
  roots: ['<rootDir>'],           // 不要加子路径！会路径翻倍
  transform: {},
  testEnvironment: 'node',
  testTimeout: 120000,            // 2分钟（云函数慢）
  maxWorkers: 1,                  // 必须串行！automator是单连接
};
