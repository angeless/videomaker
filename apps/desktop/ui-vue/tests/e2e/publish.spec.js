// @ts-check
import { test, expect } from '@playwright/test'

/**
 * Path 3: Publish panel → three tabs → content renders
 *
 * PublishView is at /create/publish with three tabs.
 * Navigate via client-side routing to preserve app state.
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

async function navigateToPublish(page) {
  // Use client-side hash navigation
  await page.evaluate(() => { window.location.hash = '#/create/publish' })
  await page.locator('.publish-view').waitFor({ timeout: 10_000 })
}

test.describe('Publish panel', () => {
  test('loads publish view with three tabs', async ({ page }) => {
    await waitForAppReady(page)
    await navigateToPublish(page)

    // View header
    const header = page.locator('.publish-view .view-header h2')
    await expect(header).toBeVisible()

    // Three tab buttons
    const tabs = page.locator('.publish-tab')
    await expect(tabs).toHaveCount(3)

    // First tab should be active by default
    const firstTab = tabs.first()
    await expect(firstTab).toHaveClass(/active/)
  })

  test('can switch between tabs', async ({ page }) => {
    await waitForAppReady(page)
    await navigateToPublish(page)

    const tabs = page.locator('.publish-tab')

    // Click "社媒导出" tab
    const exportTab = tabs.nth(1)
    await exportTab.click()
    await expect(exportTab).toHaveClass(/active/)

    // Click "内容发布" tab
    const publishTab = tabs.nth(2)
    await publishTab.click()
    await expect(publishTab).toHaveClass(/active/)
  })

  test('publish content area renders without errors', async ({ page }) => {
    await waitForAppReady(page)

    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await navigateToPublish(page)

    const content = page.locator('.publish-content')
    await expect(content).toBeVisible()

    const jsErrors = errors.filter(e => !e.includes('favicon') && !e.includes('404'))
    expect(jsErrors.length).toBe(0)
  })
})
