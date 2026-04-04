/**
 * Keyboard shortcut mappings for review mode.
 * Each entry: { key, ctrl?, shift?, meta?, modes[], action }
 * modes: which UI modes the shortcut is active in ('normal', 'drawing', 'comment', '*')
 */
export const SHORTCUT_MAP = [
  // ── Playback ──
  { key: ' ',         modes: ['normal', 'drawing'],  action: 'play_pause' },
  { key: 'k',         modes: ['normal'],              action: 'play_pause' },
  { key: 'j',         modes: ['normal'],              action: 'speed_down' },
  { key: 'l',         modes: ['normal'],              action: 'speed_up' },
  { key: 'ArrowLeft', modes: ['normal'],              action: 'prev_frame' },
  { key: 'ArrowRight',modes: ['normal'],              action: 'next_frame' },
  { key: 'ArrowLeft', modes: ['normal'], shift: true, action: 'back_5s' },
  { key: 'ArrowRight',modes: ['normal'], shift: true, action: 'forward_5s' },

  // ── I/O Loop ──
  { key: 'i',         modes: ['normal'],              action: 'set_loop_in' },
  { key: 'o',         modes: ['normal'],              action: 'set_loop_out' },
  { key: 'l',         modes: ['normal'], meta: true,  action: 'toggle_loop' },

  // ── Comments ──
  { key: 'c',         modes: ['normal'],              action: 'open_comment' },
  { key: '[',         modes: ['normal'],              action: 'prev_comment' },
  { key: ']',         modes: ['normal'],              action: 'next_comment' },
  { key: '1',         modes: ['comment'],             action: 'comment_type_1' },
  { key: '2',         modes: ['comment'],             action: 'comment_type_2' },
  { key: '3',         modes: ['comment'],             action: 'comment_type_3' },
  { key: '4',         modes: ['comment'],             action: 'comment_type_4' },
  { key: '5',         modes: ['comment'],             action: 'comment_type_5' },
  { key: '6',         modes: ['comment'],             action: 'comment_type_6' },
  { key: '7',         modes: ['comment'],             action: 'comment_type_7' },
  { key: 'Enter',     modes: ['comment'], meta: true, action: 'submit_comment' },

  // ── Drawing ──
  { key: 'd',         modes: ['normal'],              action: 'enter_drawing' },
  { key: 'z',         modes: ['drawing'], meta: true, action: 'undo' },
  { key: 'z',         modes: ['drawing'], meta: true, shift: true, action: 'redo' },

  // ── View ──
  { key: 'f',         modes: ['normal'],              action: 'toggle_fullscreen' },
  { key: 'r',         modes: ['normal'],              action: 'cycle_safe_zone' },
  { key: '=',         modes: ['normal'], meta: true,  action: 'zoom_in' },
  { key: '-',         modes: ['normal'], meta: true,  action: 'zoom_out' },
  { key: '0',         modes: ['normal'], meta: true,  action: 'zoom_reset' },

  // ── Versions ──
  { key: '[',         modes: ['normal'], meta: true,  action: 'prev_version' },
  { key: ']',         modes: ['normal'], meta: true,  action: 'next_version' },

  // ── Timeline ──
  { key: '=',         modes: ['normal'], ctrl: true,  action: 'timeline_zoom_in' },
  { key: '-',         modes: ['normal'], ctrl: true,  action: 'timeline_zoom_out' },

  // ── Global escape ──
  { key: 'Escape',    modes: ['*'],                   action: 'escape' },
]

export const COMMENT_TYPES = [
  { key: '1', type: 'cut',        label: '剪切', color: '#ef4444', icon: '🔴' },
  { key: '2', type: 'keep',       label: '保留', color: '#22c55e', icon: '🟢' },
  { key: '3', type: 'modify',     label: '修改', color: '#3b82f6', icon: '🔵' },
  { key: '4', type: 'transition', label: '转场', color: '#eab308', icon: '🟡' },
  { key: '5', type: 'audio',      label: '音频', color: '#a855f7', icon: '🟣' },
  { key: '6', type: 'subtitle',   label: '字幕', color: '#78716c', icon: '🟤' },
  { key: '7', type: 'general',    label: '通用', color: '#9ca3af', icon: '⚪' },
]
