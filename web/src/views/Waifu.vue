<script setup>
import { ref, onMounted } from "vue";

const image = ref(null);
const error = ref(null);
const loading = ref(false);

function loadWaifuImage() {
  loading.value = true;
  error.value = null;

  // Public endpoint, no API key: sends Access-Control-Allow-Origin: *, so this
  // is called directly from the browser, no backend proxy required.
  fetch("https://api.waifu.im/images")
    .then((response) => {
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return response.json();
    })
    .then((json) => {
      image.value = json.items[0];
    })
    .catch((err) => {
      error.value = err.message;
    })
    .finally(() => {
      loading.value = false;
    });
}

onMounted(loadWaifuImage);
</script>

<template>
  <h1>Waifu image</h1>
  <p class="lede">Fetched client-side from api.waifu.im, no proxy involved.</p>
  <section class="card">
    <h2>Waifu.im</h2>
    <img v-if="image" :src="image.url" :alt="`Image ${image.id}`" class="waifu-img" />
    <p v-else-if="!error">Loading&hellip;</p>
    <button type="button" @click="loadWaifuImage" :disabled="loading">
      {{ loading ? "Loading\u2026" : "Get another" }}
    </button>
  </section>
  <footer id="status" :class="{ error: error }">
    {{ error ? `Could not load image: ${error}` : image ? `Image #${image.id}` : "" }}
  </footer>
</template>
