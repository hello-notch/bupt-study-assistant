<script setup lang="ts">
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <svg
    class="icon-glyph"
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'today'">
      <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </template>
    <template v-else-if="name === 'tasks'">
      <circle cx="12" cy="12" r="9" /><path d="m8.5 12 2.2 2.2 4.8-5" />
    </template>
    <template v-else-if="name === 'courses'">
      <rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" />
    </template>
    <template v-else-if="name === 'campus'">
      <path d="m3 10 9-6 9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 20h18" />
    </template>
    <template v-else-if="name === 'electricity'">
      <path d="M13 2 5.5 13h6L11 22l7.5-12h-6L13 2Z" />
    </template>
    <template v-else-if="name === 'assistant'">
      <path d="m12 3-1.1 3.2a3 3 0 0 1-1.9 1.9L6 9.2l3 1.1a3 3 0 0 1 1.9 1.9L12 15l1.1-2.8a3 3 0 0 1 1.9-1.9l3-1.1-3-1.1a3 3 0 0 1-1.9-1.9L12 3Z" /><path d="m5 15-.6 1.7a2 2 0 0 1-1.2 1.2L2 18.3l1.2.4a2 2 0 0 1 1.2 1.2L5 21.5l.6-1.6a2 2 0 0 1 1.2-1.2l1.2-.4-1.2-.4a2 2 0 0 1-1.2-1.2L5 15Z" />
    </template>
    <template v-else-if="name === 'bell'">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1V21H9.6v-.08a1.7 1.7 0 0 0-1.08-1.54 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4H3V9.6h.08A1.7 1.7 0 0 0 4.62 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1V3h4v.08A1.7 1.7 0 0 0 15.5 4.62a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.14.4.36.75.6 1 .26.26.62.4 1 .4h.08v4H21a1.7 1.7 0 0 0-1.6.6Z" />
    </template>
    <template v-else-if="name === 'more'">
      <circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14" /></template>
    <template v-else-if="name === 'search'"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></template>
    <template v-else-if="name === 'clock'"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></template>
    <template v-else-if="name === 'map'"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2" /></template>
    <template v-else-if="name === 'arrow-right'"><path d="M5 12h14m-6-6 6 6-6 6" /></template>
    <template v-else-if="name === 'chevron-left'"><path d="m15 18-6-6 6-6" /></template>
    <template v-else-if="name === 'chevron-right'"><path d="m9 18 6-6-6-6" /></template>
    <template v-else-if="name === 'trash'"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3" /></template>
    <template v-else-if="name === 'upload'"><path d="M12 16V4m-4 4 4-4 4 4M4 15v5h16v-5" /></template>
    <template v-else-if="name === 'send'"><path d="m22 2-7 20-4-9-9-4 20-7Z" /><path d="M22 2 11 13" /></template>
    <template v-else-if="name === 'close'"><path d="m6 6 12 12M18 6 6 18" /></template>
    <template v-else-if="name === 'check'"><path d="m5 12 4 4L19 6" /></template>
    <template v-else-if="name === 'book'"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5v13Z" /><path d="M8 7h8M8 11h6" /></template>
    <template v-else-if="name === 'external'"><path d="M15 3h6v6M10 14 21 3M18 13v7H4V6h7" /></template>
    <template v-else-if="name === 'refresh'"><path d="M20 7v5h-5M4 17v-5h5" /><path d="M18.5 10a7 7 0 0 0-12-3L4 10M5.5 14a7 7 0 0 0 12 3l2.5-3" /></template>
    <template v-else-if="name === 'moon'"><path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" /></template>
    <template v-else><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></template>
  </svg>
</template>
