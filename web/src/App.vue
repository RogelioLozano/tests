<script setup>
</script>

<template>
  <main>
    <nav class="tabs">
      <RouterLink to="/">Dashboard</RouterLink>
      <RouterLink to="/about">About</RouterLink>
      <RouterLink to="/waifu">Waifu</RouterLink>
    </nav>
    <div id="view">
      <RouterView />
    </div>
  </main>
</template>
