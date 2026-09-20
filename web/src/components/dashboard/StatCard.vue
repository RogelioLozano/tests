<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  hint: { type: String, default: "" },
});
</script>

<template>
  <div class="rounded-xl border border-border bg-card p-4">
    <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
      {{ label }}
    </p>
    <p class="mt-2 text-2xl font-semibold tabular-nums">{{ value }}</p>
    <p v-if="hint" class="mt-1 truncate text-xs text-muted-foreground">{{ hint }}</p>
  </div>
</template>
