<script setup>
import { onMounted, ref } from "vue";
import { getConnection } from "./api/github";

// A deployment without an OAuth app has no working GitHub tab, so the link is
// hidden rather than left to fail when clicked.
const githubAvailable = ref(false);

onMounted(async () => {
  try {
    githubAvailable.value = (await getConnection()).available;
  } catch {
    // Optional feature; leaving the tab hidden is the safe outcome.
  }
});
</script>

<template>
  <main>
    <nav class="tabs">
      <RouterLink to="/">Dashboard</RouterLink>
      <RouterLink to="/about">About</RouterLink>
      <RouterLink to="/waifu">Waifu</RouterLink>
      <RouterLink to="/animations">Animations</RouterLink>
      <RouterLink v-if="githubAvailable" to="/github">GitHub</RouterLink>
    </nav>
    <div id="view">
      <RouterView />
    </div>
  </main>
</template>
