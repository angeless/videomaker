/**
 * Convenience composable for API access
 */
import { useApiStore } from '../stores/api.js'

export function useApi() {
  const store = useApiStore()
  return {
    api: store.api,
    bootstrap: store.bootstrap,
    sessionReady: store.sessionReady,
  }
}
