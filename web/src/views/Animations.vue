<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
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
} from "../api/animations";

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
  <h1>Animations</h1>
  <p class="lede">
    Describe a scene; the backend generates Manim code, checks it, and renders it.
  </p>

  <section class="card">
    <h2>New animation</h2>
    <div v-if="requiresKey" class="access">
      <label for="access-code">Access code</label>
      <input
        id="access-code"
        v-model="accessCode"
        type="password"
        autocomplete="off"
        placeholder="required to submit a prompt"
        @blur="verifyCode"
        @keyup.enter="verifyCode"
      />
      <span class="code-state" :data-state="codeState">
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
      <p class="lede access-note">
        Browsing is open to everyone; submitting a prompt needs a code because it
        costs model tokens and CPU.
      </p>
    </div>
    <form @submit.prevent="submit">
      <textarea
        v-model="prompt"
        rows="3"
        :maxlength="maxPromptChars"
        placeholder="e.g. plot a sine wave in green"
        :disabled="submitting"
      ></textarea>
      <div class="controls">
        <select v-if="qualities.length > 1" v-model="quality" :disabled="submitting">
          <option v-for="option in qualities" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <button type="submit" :disabled="!canSubmit">
          {{ submitting ? "Rendering\u2026" : "Render" }}
        </button>
      </div>
    </form>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <section v-if="selected" class="card">
    <h2>{{ label(selected) }}</h2>
    <video
      v-if="selected.video_url"
      :key="selected.id"
      :src="selected.video_url"
      class="animation-video"
      controls
      autoplay
      loop
      muted
      playsinline
    ></video>
    <p v-else-if="selected.status === 'failed'" class="error">
      {{ selected.error?.message }}
    </p>
    <p v-else class="lede">{{ label(selected) }}&hellip;</p>

    <p class="prompt-echo">{{ selected.prompt }}</p>
    <p v-if="selected.model" class="attribution">
      Generated by {{ selected.provider }} / {{ selected.model }}
    </p>
    <button type="button" class="link" @click="showSource">View generated code</button>
    <pre v-if="source" class="source">{{ source }}</pre>
  </section>

  <section v-if="jobs.length" class="card history">
    <h2>History</h2>
    <ul class="job-list">
      <li v-for="job in jobs" :key="job.id">
        <button
          type="button"
          :class="{ active: job.id === selectedId }"
          @click="select(job)"
        >
          <span class="job-prompt">{{ job.prompt }}</span>
          <span class="job-status" :data-status="job.status">{{ label(job) }}</span>
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
textarea,
select,
button,
input {
  font: inherit;
  color: inherit;
}

.access {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 1rem;
}

.access input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
}

.access-note {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 0.8rem;
}

.code-state {
  font-size: 0.8rem;
  color: var(--muted);
}

.code-state[data-state="valid"] {
  color: #1a7f37;
}

.code-state[data-state="invalid"] {
  color: #cf222e;
}

textarea {
  width: 100%;
  padding: 0.6rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  resize: vertical;
}

.controls {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.controls select {
  padding: 0.4rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
}

.controls button {
  padding: 0.4rem 1rem;
  border: 1px solid var(--accent);
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}

.controls button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.animation-video {
  width: 100%;
  max-width: 640px;
  border-radius: 8px;
  background: #000;
}

.prompt-echo {
  color: var(--muted);
  margin: 1rem 0 0.5rem;
}

.attribution {
  color: var(--muted);
  font-size: 0.8rem;
  margin: 0 0 0.5rem;
}

.link {
  border: 0;
  background: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
}

.source {
  margin-top: 1rem;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.8rem;
}

.history {
  margin-top: 1rem;
}

.job-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.job-list button {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
  padding: 0.5rem;
  border: 1px solid transparent;
  border-radius: 8px;
  background: none;
  text-align: left;
  cursor: pointer;
}

.job-list button.active {
  border-color: var(--line);
}

.job-prompt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-status {
  color: var(--muted);
  font-size: 0.85rem;
  white-space: nowrap;
}

.job-status[data-status="failed"] {
  color: #cf222e;
}
</style>
