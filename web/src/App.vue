<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { getConnection } from "./api/github";
import { Button } from "@/components/ui/button";

// A deployment without an OAuth app has no working GitHub tab, so the link is
// hidden rather than left to fail when clicked.
const githubAvailable = ref(false);
const route = useRoute();

const navItems = computed(() => {
  const items = [
    { to: "/", label: "Dashboard" },
    { to: "/about", label: "About" },
    { to: "/waifu", label: "Waifu" },
    { to: "/animations", label: "Animations" },
  ];
  if (githubAvailable.value) {
    // Also where the OAuth callback lands the browser once it is done.
    items.push({ to: "/github", label: "GitHub" });
  }
  return items;
});

onMounted(async () => {
  try {
    githubAvailable.value = (await getConnection()).available;
  } catch {
    // Optional feature; leaving the tab hidden is the safe outcome.
  }
});
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <aside
      class="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-sidebar p-4 text-sidebar-foreground md:flex"
    >
      <h1 class="mb-4 px-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Quarterly Figures
      </h1>
      <Button
        v-for="item in navItems"
        :key="item.to"
        as-child
        :variant="route.path === item.to ? 'secondary' : 'ghost'"
        class="justify-start"
      >
        <RouterLink :to="item.to">{{ item.label }}</RouterLink>
      </Button>
    </aside>

    <div class="flex flex-1 flex-col">
      <nav class="flex gap-1 overflow-x-auto border-b border-border p-2 md:hidden">
        <Button
          v-for="item in navItems"
          :key="item.to"
          as-child
          :variant="route.path === item.to ? 'secondary' : 'ghost'"
          size="sm"
        >
          <RouterLink :to="item.to">{{ item.label }}</RouterLink>
        </Button>
      </nav>
      <main id="view" class="flex-1 p-6 md:p-10">
        <RouterView />
      </main>
    </div>
  </div>
</template>
