// Jest configuration for miniprogram-automator tests
module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/tests/miniapp/specs/**/*.test.js'],
  testTimeout: 60000,
  verbose: true,
  reporters: [
    'default',
    ['jest-json-reporter', { outputFile: 'reports/jest-results.json' }],
  ],
  globals: {
    WECHAT_DEVTOOL_PATH: process.env.WECHAT_DEVTOOL_PATH || '',
    MINIPROGRAM_PATH: process.env.MINIPROGRAM_PATH || './miniprogram',
  },
};
