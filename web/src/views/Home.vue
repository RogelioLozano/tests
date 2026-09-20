<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { CONNECT_MESSAGES, disconnect, getConnection, listRepositories } from "@/api/github";
import AnimationsPanel from "@/components/dashboard/AnimationsPanel.vue";
import GithubAccountCard from "@/components/dashboard/GithubAccountCard.vue";
import RepositoryList from "@/components/dashboard/RepositoryList.vue";
import StatCard from "@/components/dashboard/StatCard.vue";
import WaifuCard from "@/components/dashboard/WaifuCard.vue";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const connection = ref({ available: true, connected: false });
const repositories = ref([]);
const notice = ref(null);
const error = ref(null);
const busy = ref(false);

const stats = computed(() => {
  const repos = repositories.value;
  const stars = repos.reduce((sum, repo) => sum + (repo.stars ?? 0), 0);
  const forks = repos.reduce((sum, repo) => sum + (repo.forks ?? 0), 0);
  const languages = new Map();
  for (const repo of repos) {
    if (repo.language) languages.set(repo.language, (languages.get(repo.language) ?? 0) + 1);
  }
  const topLanguage = [...languages.entries()].sort((a, b) => b[1] - a[1])[0];
  return {
    repoCount: repos.length,
    stars,
    forks,
    topLanguage: topLanguage ? topLanguage[0] : "\u2014",
  };
});

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
  <div class="mx-auto max-w-6xl space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Repository overview</h1>
        <p class="text-sm text-muted-foreground">
          Connect a GitHub account to see its public repositories and metrics.
        </p>
      </div>
      <GithubAccountCard :connection="connection" :busy="busy" @disconnect="revoke" />
    </header>

    <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
    <p v-if="notice" class="text-sm text-muted-foreground">{{ notice }}</p>

    <p v-if="loading" class="text-sm text-muted-foreground">Checking&hellip;</p>

    <template v-else>
      <div
        v-if="connection.connected"
        class="grid grid-cols-2 gap-4 lg:grid-cols-4"
      >
        <StatCard label="Repositories" :value="stats.repoCount" />
        <StatCard label="Total stars" :value="stats.stars" />
        <StatCard label="Total forks" :value="stats.forks" />
        <StatCard label="Top language" :value="stats.topLanguage" />
      </div>

      <div class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card v-if="connection.connected">
          <CardHeader>
            <CardTitle>Public repositories ({{ repositories.length }})</CardTitle>
          </CardHeader>
          <CardContent>
            <RepositoryList :repositories="repositories" />
          </CardContent>
        </Card>

        <Card v-else-if="connection.available">
          <CardHeader>
            <CardTitle>Delegate access</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3 text-sm">
            <p>
              You will be sent to GitHub to approve this. Nothing is shared until
              you do, and you can withdraw it at any time.
            </p>
            <ul class="list-disc space-y-1 pl-5 text-muted-foreground">
              <li><strong class="text-foreground">Read</strong> the public repositories on your account</li>
              <li><strong class="text-foreground">No write access</strong> of any kind is requested</li>
              <li><strong class="text-foreground">No private data</strong> &mdash; no private repos, no email</li>
            </ul>
            <p class="text-xs text-muted-foreground">
              The access token is kept on the server and never reaches this page.
            </p>
          </CardContent>
        </Card>

        <Card v-else>
          <CardHeader>
            <CardTitle>Not configured</CardTitle>
          </CardHeader>
          <CardContent class="text-sm text-muted-foreground">
            This deployment has no GitHub OAuth app, so the feature is switched off.
          </CardContent>
        </Card>

        <WaifuCard />
      </div>

      <AnimationsPanel />
    </template>
  </div>
</template>
