// @ts-check
import { test, expect } from '@playwright/test'

/**
 * Path 5: Settings page → AI provider dropdown → save button
 *
 * After app startup, navigate to settings using the nav link (client-side routing).
 * SettingsView has AI config card + platform connections card.
 */

async function waitForAppReady(page) {
  await page.goto('/')
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

/** Navigate to settings via client-side hash routing. */
async function navigateToSettings(page) {
  await page.evaluate(() => { window.location.hash = '#/settings' })
  await page.locator('h2').first().waitFor({ timeout: 10_000 })
}

test.describe('Settings page', () => {
  test('loads settings page with AI configuration', async ({ page }) => {
    await waitForAppReady(page)
    await navigateToSettings(page)

    // Page heading
    const heading = page.locator('h2').first()
    await expect(heading).toBeVisible()

    // AI config card with provider select
    const providerSelect = page.locator('select.form-select').first()
    await expect(providerSelect).toBeVisible()
  })

  test('AI provider dropdown has options', async ({ page }) => {
    await waitForAppReady(page)
    await navigateToSettings(page)

    const providerSelect = page.locator('select.form-select').first()
    await expect(providerSelect).toBeVisible({ timeout: 10_000 })

    const options = providerSelect.locator('option')
    const count = await options.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('save button exists and is clickable', async ({ page }) => {
    await waitForAppReady(page)
    await navigateToSettings(page)

    // Find the first save button (AI config save)
    const saveBtn = page.locator('button.btn-primary', { hasText: /保存|save/i }).first()
    await expect(saveBtn).toBeVisible({ timeout: 10_000 })
    await expect(saveBtn).toBeEnabled()
  })

  test('platform connections section renders', async ({ page }) => {
    await waitForAppReady(page)
    await navigateToSettings(page)

    // Wait for cards to appear
    const cards = page.locator('.card')
    await cards.first().waitFor({ timeout: 10_000 })
    const cardCount = await cards.count()
    // At least 2: AI config + platform connections
    expect(cardCount).toBeGreaterThanOrEqual(2)
  })
})
