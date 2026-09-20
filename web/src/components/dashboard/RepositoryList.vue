<script setup>
import { computed } from "vue";
import { ExternalLink, GitFork, Star } from "@lucide/vue";
import { Badge } from "@/components/ui/badge";

const props = defineProps({
  repositories: { type: Array, required: true },
});

function when(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// Cycles through the theme's chart palette so the bars stay on-brand without
// hardcoding colors here.
const languageBreakdown = computed(() => {
  const counts = new Map();
  for (const repo of props.repositories) {
    if (!repo.language) continue;
    counts.set(repo.language, (counts.get(repo.language) ?? 0) + 1);
  }
  const total = [...counts.values()].reduce((sum, n) => sum + n, 0);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([language, count], index) => ({
      language,
      count,
      percent: total ? Math.round((count / total) * 100) : 0,
      color: `var(--chart-${(index % 5) + 1})`,
    }));
});
</script>

<template>
  <div class="space-y-6">
    <div v-if="languageBreakdown.length" class="space-y-2">
      <p class="text-sm font-medium text-muted-foreground">Top languages</p>
      <div class="space-y-1.5">
        <div
          v-for="item in languageBreakdown"
          :key="item.language"
          class="flex items-center gap-3 text-sm"
        >
          <span class="w-24 shrink-0 truncate">{{ item.language }}</span>
          <div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              class="h-full rounded-full"
              :style="{ width: item.percent + '%', background: item.color }"
            ></div>
          </div>
          <span class="w-8 shrink-0 text-right text-muted-foreground">{{ item.count }}</span>
        </div>
      </div>
    </div>

    <ul v-if="repositories.length" class="divide-y divide-border">
      <li
        v-for="repo in repositories"
        :key="repo.full_name"
        class="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0"
      >
        <div class="min-w-0">
          <a
            :href="repo.url"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1.5 font-medium hover:underline"
          >
            {{ repo.name }}
            <ExternalLink class="size-3.5 text-muted-foreground" />
          </a>
          <Badge v-if="repo.is_fork" variant="secondary" class="ml-2 align-middle">fork</Badge>
          <p v-if="repo.description" class="mt-1 truncate text-sm text-muted-foreground">
            {{ repo.description }}
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            <span v-if="repo.language">{{ repo.language }} &middot; </span>
            <span v-if="repo.pushed_at">updated {{ when(repo.pushed_at) }}</span>
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-3 text-sm text-muted-foreground">
          <span class="inline-flex items-center gap-1"><Star class="size-3.5" />{{ repo.stars }}</span>
          <span class="inline-flex items-center gap-1"><GitFork class="size-3.5" />{{ repo.forks }}</span>
        </div>
      </li>
    </ul>
    <p v-else class="text-sm text-muted-foreground">This account has no public repositories.</p>
  </div>
</template>
