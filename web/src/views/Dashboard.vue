<script setup>
import { ref, onMounted } from "vue";

const data = ref(null);
const error = ref(null);

function formatMoney(amount, currency) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

onMounted(() => {
  fetch("/api/data.json", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return response.json();
    })
    .then((json) => {
      data.value = json;
    })
    .catch((err) => {
      error.value = err.message;
    });
});
</script>

<template>
  <h1>Quarterly figures</h1>
  <p class="lede">A Vue build served from static files, no server rendering.</p>
  <section class="card">
    <h2>Revenue</h2>
    <dl>
      <dt>Quarter</dt>
      <dd>{{ data ? data.quarter : "\u2026" }}</dd>
      <dt>Total</dt>
      <dd class="total">{{ data ? formatMoney(data.revenue, data.currency) : "\u2026" }}</dd>
    </dl>
  </section>
  <footer id="status" :class="{ error: error }">
    {{ error ? `Could not load /api/data.json: ${error}` : data ? "Loaded." : "Loading\u2026" }}
  </footer>
</template>
