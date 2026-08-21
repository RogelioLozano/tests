import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "../views/Dashboard.vue";
import About from "../views/About.vue";
import NotFound from "../views/NotFound.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Dashboard },
    { path: "/about", component: About },
    { path: "/:pathMatch(.*)*", component: NotFound },
  ],
});
