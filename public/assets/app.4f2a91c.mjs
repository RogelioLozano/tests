const els = {
  quarter: document.getElementById("quarter"),
  revenue: document.getElementById("revenue"),
  status: document.getElementById("status"),
};

function formatMoney(amount, currency) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

async function load() {
  const response = await fetch("/data.json", { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

load()
  .then((data) => {
    // textContent, never innerHTML: the payload is data, so it must never be
    // able to become markup.
    els.quarter.textContent = data.quarter;
    els.revenue.textContent = formatMoney(data.revenue, data.currency);
    els.status.textContent = "Loaded over TLS.";
  })
  .catch((error) => {
    els.status.textContent = `Could not load /data.json: ${error.message}`;
    els.status.classList.add("error");
  });
