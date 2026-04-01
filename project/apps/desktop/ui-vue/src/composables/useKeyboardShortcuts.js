/**
 * Keyboard shortcuts composable for review mode.
 * Mode-aware: shortcuts only fire when the current UI mode matches.
 * Disabled when an input/textarea is focused.
 */
import { onMounted, onUnmounted } from 'vue'
import { SHORTCUT_MAP } from '../config/shortcuts.js'

/**
 * @param {import('vue').Ref<string>} modeRef - current UI mode ('normal'|'drawing'|'comment')
 * @param {Record<string, Function>} handlers - map of action name → handler function
 */
export function useKeyboardShortcuts(modeRef, handlers) {
  function onKeyDown(e) {
    // Skip when user is typing in input/textarea
    const tag = (e.target?.tagName || '').toLowerCase()
    if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) {
      // Allow Escape and Cmd+Enter even in inputs
      if (e.key !== 'Escape' && !(e.key === 'Enter' && e.metaKey)) return
    }

    const currentMode = modeRef.value

    for (const shortcut of SHORTCUT_MAP) {
      // Mode check
      if (!shortcut.modes.includes('*') && !shortcut.modes.includes(currentMode)) continue

      // Key match
      if (e.key !== shortcut.key) continue

      // Modifier checks
      if (!!shortcut.meta !== e.metaKey) continue
      if (!!shortcut.ctrl !== e.ctrlKey) continue
      if (!!shortcut.shift !== e.shiftKey) continue

      // Found match — execute handler
      const handler = handlers[shortcut.action]
      if (handler) {
        e.preventDefault()
        handler(e)
        return
      }
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', onKeyDown)
  })

  return { SHORTCUT_MAP }
}
