// @ts-check
import { test, expect } from '@playwright/test'

/**
 * Path 2: Library → search → results display
 *
 * After startup, if no project is loaded, the app auto-navigates to /library.
 * The onboarding modal may appear — we dismiss it first.
 */

/** Wait for app startup to complete and dismiss onboarding if shown. */
async function waitForAppReady(page) {
  await page.goto('/')
  // Wait for auto-navigation after startup
  await page.waitForURL(/#\/(library|create)/, { timeout: 20_000 })
  // Dismiss onboarding if it appears
  const modal = page.locator('.modal-overlay')
  if (await modal.isVisible().catch(() => false)) {
    const skipBtn = modal.locator('button', { hasText: /跳过|skip/i })
    if (await skipBtn.isVisible().catch(() => false)) {
      await skipBtn.click()
      await expect(modal).not.toBeVisible({ timeout: 5_000 })
    }
  }
}

test.describe('Library page', () => {
  test('loads library page with search bar and stats', async ({ page }) => {
    await waitForAppReady(page)
    await page.goto('/#/library')
    await page.waitForLoadState('networkidle')

    // Search toolbar should be visible
    const toolbar = page.locator('.library-toolbar')
    await expect(toolbar).toBeVisible({ timeout: 10_000 })

    // Stats bar should be visible
    const stats = page.locator('.library-stats')
    await expect(stats).toBeVisible()
  })

  test('search controls are functional', async ({ page }) => {
    await waitForAppReady(page)
    await page.goto('/#/library')
    await page.waitForLoadState('networkidle')

    // Search mode selector should exist with options
    const searchModeSelect = page.locator('.toolbar-controls select').first()
    await expect(searchModeSelect).toBeVisible({ timeout: 10_000 })

    // Media type selector
    const mediaTypeSelect = page.locator('.toolbar-controls select').nth(1)
    await expect(mediaTypeSelect).toBeVisible()

    // Search button should exist
    const searchBtn = page.locator('.toolbar-controls button', { hasText: '搜索' })
    await expect(searchBtn).toBeVisible()
  })

  test('search button triggers search without error', async ({ page }) => {
    await waitForAppReady(page)
    await page.goto('/#/library')
    await page.waitForLoadState('networkidle')

    // Wait for toolbar to load
    await page.locator('.library-toolbar').waitFor({ timeout: 10_000 })

    // Track console errors
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    // Click search — use force:true in case of minor overlay
    const searchBtn = page.locator('.toolbar-controls button', { hasText: '搜索' })
    await searchBtn.click({ force: true })

    // Wait for network response
    await page.waitForTimeout(2_000)

    // No fatal JS errors (ignore favicon/404 noise)
    const jsErrors = errors.filter(e => !e.includes('favicon') && !e.includes('404'))
    expect(jsErrors.length).toBe(0)
  })
})
