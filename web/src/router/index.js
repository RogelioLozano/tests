import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "../views/Dashboard.vue";
import About from "../views/About.vue";
import Waifu from "../views/Waifu.vue";
import Animations from "../views/Animations.vue";
import GitHub from "../views/GitHub.vue";
import NotFound from "../views/NotFound.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Dashboard },
    { path: "/about", component: About },
    { path: "/waifu", component: Waifu },
    { path: "/animations", component: Animations },
    // Also where the OAuth callback lands the browser once it is done.
    { path: "/github", component: GitHub },
    { path: "/:pathMatch(.*)*", component: NotFound },
  ],
});
