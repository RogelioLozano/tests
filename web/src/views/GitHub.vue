<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  CONNECT_MESSAGES,
  LOGIN_URL,
  disconnect,
  getConnection,
  listRepositories,
} from "../api/github";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const connection = ref({ available: true, connected: false });
const repositories = ref([]);
const notice = ref(null);
const error = ref(null);
const busy = ref(false);

async function load() {
  try {
    connection.value = await getConnection();
    if (connection.value.connected) await loadRepositories();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function loadRepositories() {
  try {
    repositories.value = (await listRepositories()).items;
  } catch (err) {
    error.value = err.message;
  }
}

async function revoke() {
  busy.value = true;
  error.value = null;
  try {
    await disconnect();
    connection.value = { ...connection.value, connected: false, login: null };
    repositories.value = [];
    notice.value = "Disconnected. The stored token has been deleted.";
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function when(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

onMounted(() => {
  const outcome = route.query.connect;
  if (outcome && outcome !== "ok") {
    error.value = CONNECT_MESSAGES[outcome] ?? "Sign-in did not complete.";
  }
  // Drop the marker so a refresh does not replay the message.
  if (outcome) router.replace({ query: {} });
  load();
});
</script>

<template>
  <h1>GitHub</h1>
  <p class="lede">
    Connect a GitHub account to list its public repositories here.
  </p>

  <p v-if="loading" class="lede">Checking&hellip;</p>

  <section v-else-if="!connection.available" class="card">
    <h2>Not configured</h2>
    <p class="lede">
      This deployment has no GitHub OAuth app, so the feature is switched off.
    </p>
  </section>

  <template v-else-if="!connection.connected">
    <section class="card">
      <h2>Delegate access</h2>
      <p>
        You will be sent to GitHub to approve this. Nothing is shared until you
        do, and you can withdraw it at any time.
      </p>
      <ul class="grants">
        <li><strong>Read</strong> the public repositories on your account</li>
        <li><strong>No write access</strong> of any kind is requested</li>
        <li><strong>No private data</strong> — no private repos, no email</li>
      </ul>
      <p class="fineprint">
        The access token is kept on the server and never reaches this page.
      </p>
      <a class="connect" :href="LOGIN_URL">Connect GitHub</a>
    </section>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="lede">{{ notice }}</p>
  </template>

  <template v-else>
    <section class="card account">
      <img
        v-if="connection.avatar_url"
        class="avatar"
        :src="connection.avatar_url"
        :alt="''"
        width="40"
        height="40"
      />
      <div>
        <p class="login">{{ connection.login }}</p>
        <p class="fineprint">
          Access expires {{ when(connection.expires_at) }}
        </p>
      </div>
      <button type="button" class="link" :disabled="busy" @click="revoke">
        Disconnect
      </button>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="card">
      <h2>Public repositories ({{ repositories.length }})</h2>
      <p v-if="!repositories.length" class="lede">
        This account has no public repositories.
      </p>
      <ul v-else class="repos">
        <li v-for="repo in repositories" :key="repo.full_name">
          <a :href="repo.url" target="_blank" rel="noopener noreferrer">
            {{ repo.name }}
          </a>
          <span v-if="repo.is_fork" class="badge">fork</span>
          <p v-if="repo.description" class="repo-description">
            {{ repo.description }}
          </p>
          <p class="repo-meta">
            <span v-if="repo.language">{{ repo.language }}</span>
            <span>{{ repo.stars }} stars</span>
            <span v-if="repo.pushed_at">updated {{ when(repo.pushed_at) }}</span>
          </p>
        </li>
      </ul>
    </section>
  </template>
</template>

<style scoped>
.grants {
  margin: 1rem 0;
  padding-left: 1.1rem;
  color: var(--muted);
}

.fineprint {
  color: var(--muted);
  font-size: 0.8rem;
  margin: 0 0 1rem;
}

.connect {
  display: inline-block;
  padding: 0.4rem 1rem;
  border: 1px solid var(--accent);
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  text-decoration: none;
}

.account {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.account div {
  flex: 1;
}

.avatar {
  border-radius: 50%;
}

.login {
  font-weight: 600;
  margin: 0;
}

.account .fineprint {
  margin: 0;
}

.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
}

.link:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.repos {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.repos > li > a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.badge {
  margin-left: 0.5rem;
  padding: 0.05rem 0.4rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 0.7rem;
  color: var(--muted);
}

.repo-description {
  margin: 0.25rem 0 0;
}

.repo-meta {
  display: flex;
  gap: 1rem;
  margin: 0.25rem 0 0;
  color: var(--muted);
  font-size: 0.8rem;
}
</style>
