// @ts-check
import { test, expect } from '@playwright/test'

/**
 * Path 4: Social export → select platform tab → content renders
 *
 * Social export is the second tab in PublishView (社媒导出).
 */

async function waitForAppReady(page) {
  await page.goto('/')
  await page.waitForURL(/#\/(library|create)/, { timeout: 20_000 })
  const modal = page.locator('.modal-overlay')
  if (await modal.isVisible().catch(() => false)) {
    const skipBtn = modal.locator('button', { hasText: /跳过|skip/i })
    if (await skipBtn.isVisible().catch(() => false)) {
      await skipBtn.click()
      await expect(modal).not.toBeVisible({ timeout: 5_000 })
    }
  }
}

test.describe('Social export panel', () => {
  test('navigates to social export tab and renders content', async ({ page }) => {
    await waitForAppReady(page)
    await page.goto('/#/create/publish')
    await page.waitForLoadState('networkidle')

    // Click the second tab (社媒导出)
    const tabs = page.locator('.publish-tab')
    await tabs.first().waitFor({ timeout: 10_000 })
    await tabs.nth(1).click()

    // Wait for the SocialExport component to render
    const content = page.locator('.publish-content')
    await expect(content).toBeVisible()

    // Should have some content inside (component rendered)
    const innerContent = await content.innerHTML()
    expect(innerContent.length).toBeGreaterThan(0)
  })

  test('export tab stays active after selection', async ({ page }) => {
    await waitForAppReady(page)
    await page.goto('/#/create/publish')
    await page.waitForLoadState('networkidle')

    const tabs = page.locator('.publish-tab')
    await tabs.first().waitFor({ timeout: 10_000 })
    await tabs.nth(1).click()

    // Tab should remain active
    await expect(tabs.nth(1)).toHaveClass(/active/)

    // No console errors from the switch
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await page.waitForTimeout(1_000)
    const jsErrors = errors.filter(e => !e.includes('favicon') && !e.includes('404'))
    expect(jsErrors.length).toBe(0)
  })
})
