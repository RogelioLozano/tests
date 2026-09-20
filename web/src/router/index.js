import { createRouter, createWebHistory } from "vue-router";
import Home from "../views/Home.vue";
import NotFound from "../views/NotFound.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Home },
    // Also where the OAuth callback lands the browser once it is done.
    { path: "/github", component: Home },
    { path: "/:pathMatch(.*)*", component: NotFound },
  ],
});

