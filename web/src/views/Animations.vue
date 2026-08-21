<script setup>
import { ref } from "vue";

// Rendered by the Manim pipeline and copied into web/public/animations/.
// These files are git-ignored artifacts; regenerate them with the render command.
const videos = ref([
  { id: "square-to-circle", title: "Square to Circle", src: "/animations/SquareToCircle.mp4" },
]);

const current = ref(videos.value[0]);

function select(video) {
  current.value = video;
}
</script>

<template>
  <h1>Animations</h1>
  <p class="lede">Pre-rendered with Manim, served as static video assets.</p>
  <section class="card">
    <h2>{{ current.title }}</h2>
    <video :src="current.src" class="animation-video" controls autoplay loop muted playsinline></video>
    <nav v-if="videos.length > 1" class="animation-list">
      <button
        v-for="video in videos"
        :key="video.id"
        type="button"
        :disabled="video.id === current.id"
        @click="select(video)"
      >
        {{ video.title }}
      </button>
    </nav>
  </section>
</template>

<style scoped>
.animation-video {
  width: 100%;
  max-width: 640px;
  border-radius: 8px;
  background: #000;
}

.animation-list {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}
</style>
