<script setup>
import { RouterView } from "vue-router";
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <main id="view" class="p-6 md:p-10">
      <RouterView />
    </main>
  </div>
</template>
