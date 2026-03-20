import { computed } from 'vue'
import { useTimelineStore } from '../stores/timeline.js'

const BASE_PX_PER_SEC = 60

export function useTimeline() {
  const store = useTimelineStore()

  const pxPerSecond = computed(() => BASE_PX_PER_SEC * store.zoom)

  const totalWidth = computed(() => {
    return Math.ceil(store.totalDuration * pxPerSecond.value)
  })

  function timeToPx(seconds) {
    return seconds * pxPerSecond.value
  }

  function pxToTime(px) {
    return px / pxPerSecond.value
  }

  function clipStyle(clip) {
    const left = timeToPx(clip.timeline_start || 0)
    const width = timeToPx((clip.timeline_end || 0) - (clip.timeline_start || 0))
    return {
      left: `${left}px`,
      width: `${Math.max(width, 2)}px`,
    }
  }

  function subtitleStyle(sub) {
    const left = timeToPx(sub.start_time || 0)
    const width = timeToPx((sub.end_time || 0) - (sub.start_time || 0))
    return {
      left: `${left}px`,
      width: `${Math.max(width, 2)}px`,
    }
  }

  return {
    pxPerSecond,
    totalWidth,
    timeToPx,
    pxToTime,
    clipStyle,
    subtitleStyle,
  }
}
