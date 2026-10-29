const { test, expect } = require('@playwright/test');
const BASE = 'http://localhost:5190';

test.describe('FitTrack Admin', () => {
  test('page loads successfully', async ({ page }) => {
    const response = await page.goto(BASE, { waitUntil: 'networkidle' });
    expect(response.status()).toBe(200);
    expect(await page.title()).toBeTruthy();
  });

  test('has app container', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await expect(page.locator('#app')).toBeVisible();
  });

  test('no console errors on load', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('pageerror', err => errors.push(err.message));
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });
});

test.describe('Responsive', () => {
  test('mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await expect(page.locator('#app')).toBeVisible();
  });

  test('tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await expect(page.locator('#app')).toBeVisible();
  });
});

test.describe('Screenshot', () => {
  test('capture homepage', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.screenshot({ path: 'reports/fittrack/admin_home.png', fullPage: true });
  });
});
