<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Loader2, Sparkles } from "@lucide/vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  checkAccessCode,
  createAnimation,
  getAccessCode,
  getAnimationSource,
  getCapabilities,
  isTerminal,
  listAnimations,
  setAccessCode,
  waitForJob,
} from "@/api/animations";

const QUALITY_LABELS = {
  low: "Low (fast)",
  medium: "Medium",
  high: "High (slow)",
};

const STAGE_LABELS = {
  pending: "Queued",
  generating: "Writing the scene",
  validating: "Checking the code",
  rendering: "Rendering",
  storing: "Saving",
  succeeded: "Ready",
  failed: "Failed",
};

const STATUS_VARIANTS = {
  succeeded: "default",
  failed: "destructive",
};

const prompt = ref("");
const quality = ref("low");
// Offered qualities come from the server: a small instance has the memory for
// low only, and picking one it cannot afford would OOM the container.
const qualities = ref([{ value: "low", label: QUALITY_LABELS.low }]);
const maxPromptChars = ref(1000);
const requiresKey = ref(false);
const accessCode = ref(getAccessCode());
const codeState = ref("unknown"); // unknown | checking | valid | invalid
const jobs = ref([]);
const selectedId = ref(null);
const source = ref(null);
const submitting = ref(false);
const error = ref(null);

let poller = null;

const selected = computed(
  () => jobs.value.find((job) => job.id === selectedId.value) ?? null,
);
const canSubmit = computed(
  () =>
    prompt.value.trim().length > 0 &&
    !submitting.value &&
    (!requiresKey.value || accessCode.value.trim().length > 0),
);

function label(job) {
  return STAGE_LABELS[job.status] ?? job.status;
}

function upsert(job) {
  const index = jobs.value.findIndex((existing) => existing.id === job.id);
  if (index === -1) jobs.value = [job, ...jobs.value];
  else jobs.value[index] = job;
}

async function refresh() {
  try {
    const page = await listAnimations({ limit: 20 });
    jobs.value = page.items;
    if (!selectedId.value) {
      selectedId.value = page.items.find((job) => job.video_url)?.id ?? null;
    }
  } catch (err) {
    error.value = err.message;
  }
}

async function loadCapabilities() {
  try {
    const caps = await getCapabilities();
    qualities.value = caps.qualities.map((value) => ({
      value,
      label: QUALITY_LABELS[value] ?? value,
    }));
    maxPromptChars.value = caps.max_prompt_chars;
    requiresKey.value = caps.requires_key;
    if (!caps.qualities.includes(quality.value)) {
      quality.value = caps.default_quality ?? caps.qualities[0];
    }
    if (requiresKey.value && accessCode.value) verifyCode();
  } catch {
    // Non-fatal: the default single low option is already usable.
  }
}

// The browser cannot judge the code itself — it has nothing to compare
// against — so it asks the server.
async function verifyCode() {
  const code = accessCode.value.trim();
  if (!code) {
    codeState.value = "unknown";
    return;
  }
  codeState.value = "checking";
  try {
    const ok = await checkAccessCode(code);
    codeState.value = ok ? "valid" : "invalid";
    setAccessCode(ok ? code : "");
  } catch {
    codeState.value = "unknown";
  }
}

async function submit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;
  source.value = null;

  try {
    const job = await createAnimation(prompt.value.trim(), quality.value);
    upsert(job);
    selectedId.value = job.id;

    // The job may already be finished (inline queue) or not (worker queue);
    // polling covers both, so the view never depends on which is in play.
    const finished = isTerminal(job)
      ? job
      : await waitForJob(job.id, upsert, { signal: poller?.signal });

    if (finished) {
      upsert(finished);
      if (finished.status === "failed") {
        error.value = finished.error?.message ?? "The render failed.";
      } else {
        prompt.value = "";
      }
    }
  } catch (err) {
    error.value = err.message;
    if (err.code === "invalid_api_key" || err.code === "api_key_required") {
      codeState.value = "invalid";
    }
  } finally {
    submitting.value = false;
  }
}

function select(job) {
  selectedId.value = job.id;
  source.value = null;
}

async function showSource() {
  if (!selected.value) return;
  try {
    source.value = (await getAnimationSource(selected.value.id)).code;
  } catch (err) {
    error.value = err.message;
  }
}

onMounted(() => {
  poller = new AbortController();
  loadCapabilities();
  refresh();
});

onUnmounted(() => poller?.abort());
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <Sparkles class="size-4" />
        Animations
      </CardTitle>
      <p class="text-sm text-muted-foreground">
        Describe a scene; the backend generates Manim code, checks it, and renders it.
      </p>
    </CardHeader>
    <CardContent class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div class="space-y-6">
        <form class="space-y-3" @submit.prevent="submit">
          <div v-if="requiresKey" class="flex flex-wrap items-center gap-2">
            <label for="access-code" class="text-sm font-medium">Access code</label>
            <input
              id="access-code"
              v-model="accessCode"
              type="password"
              autocomplete="off"
              placeholder="required to submit a prompt"
              class="rounded-md border border-input bg-transparent px-2 py-1 text-sm"
              @blur="verifyCode"
              @keyup.enter="verifyCode"
            />
            <span
              class="text-xs"
              :class="{
                'text-muted-foreground': codeState === 'unknown' || codeState === 'checking',
                'text-emerald-500': codeState === 'valid',
                'text-destructive': codeState === 'invalid',
              }"
            >
              {{
                codeState === "valid"
                  ? "accepted"
                  : codeState === "invalid"
                    ? "not valid"
                    : codeState === "checking"
                      ? "checking\u2026"
                      : ""
              }}
            </span>
            <p class="w-full text-xs text-muted-foreground">
              Browsing is open to everyone; submitting a prompt needs a code because it
              costs model tokens and CPU.
            </p>
          </div>

          <textarea
            v-model="prompt"
            rows="3"
            :maxlength="maxPromptChars"
            placeholder="e.g. plot a sine wave in green"
            :disabled="submitting"
            class="w-full resize-y rounded-md border border-input bg-transparent p-2 text-sm"
          ></textarea>

          <div class="flex items-center gap-2">
            <select
              v-if="qualities.length > 1"
              v-model="quality"
              :disabled="submitting"
              class="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
            >
              <option v-for="option in qualities" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <Button type="submit" :disabled="!canSubmit" size="sm">
              <Loader2 v-if="submitting" class="size-4 animate-spin" />
              {{ submitting ? "Rendering\u2026" : "Render" }}
            </Button>
          </div>
          <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
        </form>

        <div v-if="selected" class="space-y-2 border-t border-border pt-4">
          <div class="flex items-center gap-2">
            <h3 class="text-sm font-medium">{{ label(selected) }}</h3>
            <Badge v-if="selected.status !== 'succeeded'" variant="outline">{{ selected.status }}</Badge>
          </div>
          <video
            v-if="selected.video_url"
            :key="selected.id"
            :src="selected.video_url"
            class="w-full max-w-xl rounded-md bg-black"
            controls
            autoplay
            loop
            muted
            playsinline
          ></video>
          <p v-else-if="selected.status === 'failed'" class="text-sm text-destructive">
            {{ selected.error?.message }}
          </p>
          <p v-else class="text-sm text-muted-foreground">{{ label(selected) }}&hellip;</p>

          <p class="text-sm text-muted-foreground">{{ selected.prompt }}</p>
          <p v-if="selected.model" class="text-xs text-muted-foreground">
            Generated by {{ selected.provider }} / {{ selected.model }}
          </p>
          <Button variant="link" size="sm" class="h-auto p-0" @click="showSource">
            View generated code
          </Button>
          <pre v-if="source" class="overflow-x-auto rounded-md border border-border p-3 text-xs">{{ source }}</pre>
        </div>
      </div>

      <div v-if="jobs.length" class="space-y-2">
        <p class="text-sm font-medium text-muted-foreground">History</p>
        <ul class="space-y-1">
          <li v-for="job in jobs" :key="job.id">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
              :class="{ 'bg-accent': job.id === selectedId }"
              @click="select(job)"
            >
              <span class="truncate">{{ job.prompt }}</span>
              <Badge :variant="STATUS_VARIANTS[job.status] ?? 'secondary'" class="shrink-0">
                {{ label(job) }}
              </Badge>
            </button>
          </li>
        </ul>
      </div>
    </CardContent>
  </Card>
</template>
