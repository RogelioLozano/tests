<script setup>
import { onMounted, ref } from "vue";
import { RefreshCw } from "@lucide/vue";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";

const image = ref(null);
const error = ref(null);
const loading = ref(false);

function load() {
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

onMounted(load);
</script>

<template>
  <Card class="gap-0 overflow-hidden py-0">
    <div class="relative aspect-[4/5] w-full bg-muted">
      <img
        v-if="image"
        :src="image.url"
        :alt="`Image ${image.id}`"
        class="size-full object-cover"
      />
      <div v-else class="flex size-full items-center justify-center px-4 text-center text-sm text-muted-foreground">
        {{ error ? "Could not load image" : "Loading\u2026" }}
      </div>
      <Button
        size="icon"
        variant="secondary"
        class="absolute right-2 top-2 shadow"
        :disabled="loading"
        title="Get another"
        @click="load"
      >
        <RefreshCw class="size-4" :class="{ 'animate-spin': loading }" />
      </Button>
    </div>
    <CardHeader class="px-4 py-4">
      <CardTitle class="text-sm">Waifu of the moment</CardTitle>
      <p class="text-xs text-muted-foreground">
        {{ error ? error : image ? `Image #${image.id}` : "" }}
      </p>
    </CardHeader>
  </Card>
</template>
