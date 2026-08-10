const view = document.getElementById("view");
const status = document.getElementById("status");

function formatMoney(amount, currency) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

async function loadRevenue() {
  const response = await fetch("/data.json", { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function renderDashboard() {
  document.title = "Quarterly figures";
  // Markup we authored ourselves, not fetched data, so innerHTML is safe here.
  view.innerHTML = `
    <h1>Quarterly figures</h1>
    <p class="lede">A built bundle served from <code>public/</code> over TLS.</p>
    <section class="card">
      <h2>Revenue</h2>
      <dl>
        <dt>Quarter</dt>
        <dd id="quarter">&hellip;</dd>
        <dt>Total</dt>
        <dd id="revenue" class="total">&hellip;</dd>
      </dl>
    </section>
  `;
  status.textContent = "Loading\u2026";
  status.classList.remove("error");
  loadRevenue()
    .then((data) => {
      // textContent, never innerHTML: the payload is data, so it must never be
      // able to become markup.
      view.querySelector("#quarter").textContent = data.quarter;
      view.querySelector("#revenue").textContent = formatMoney(data.revenue, data.currency);
      status.textContent = "Loaded over TLS.";
    })
    .catch((error) => {
      status.textContent = `Could not load /data.json: ${error.message}`;
      status.classList.add("error");
    });
}

function renderAbout() {
  document.title = "About";
  view.innerHTML = `
    <h1>About</h1>
    <p class="lede">A second route rendered client-side, no page reload or server round trip.</p>
  `;
  status.textContent = "";
  status.classList.remove("error");
}

function renderNotFound() {
  document.title = "Not found";
  view.innerHTML = `
    <h1>Not found</h1>
    <p class="lede">There is no client-side route for this path.</p>
  `;
  status.textContent = "";
}

const routes = {
  "/": renderDashboard,
  "/about": renderAbout,
};

function render(pathname) {
  (routes[pathname] || renderNotFound)();
  for (const link of document.querySelectorAll("nav.tabs a")) {
    link.setAttribute("aria-current", link.getAttribute("href") === pathname ? "page" : "false");
  }
}

// Intercept in-app links so navigation swaps the view instead of reloading the page.
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-link]");
  if (!link) return;
  const url = new URL(link.href);
  if (url.origin !== location.origin) return;
  event.preventDefault();
  if (url.pathname === location.pathname) return;
  history.pushState(null, "", url.pathname);
  render(url.pathname);
});

// Back/forward buttons change the URL without a click, so they need their own hook.
window.addEventListener("popstate", () => render(location.pathname));

render(location.pathname);
