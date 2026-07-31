// 产品端与管理端使用独立入口和会话守卫，角色判断最终仍以服务端为准。
import { createRouter, createWebHistory } from "vue-router";

const legacyModePath: Record<string, string> = {
  chat: "/chat",
  interview: "/interviews",
  report: "/profile",
  learning: "/learning",
  history: "/history",
  resume: "/resumes",
  review: "/reviews",
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: () => legacyModePath[localStorage.getItem("interview-lab-mode") || ""] || "/today",
    },
    {
      path: "/today",
      name: "today",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "today" },
    },
    {
      path: "/chat/:sessionId?",
      name: "chat",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "chat" },
    },
    {
      path: "/interviews/:interviewId?",
      name: "interviews",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "interview" },
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "report" },
    },
    {
      path: "/learning",
      name: "learning",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "learning" },
    },
    {
      path: "/history",
      name: "history",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "history" },
    },
    {
      path: "/resumes/:resumeId?",
      name: "resumes",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "resume" },
    },
    {
      path: "/reviews/:reviewId?",
      name: "reviews",
      component: () => import("@/views/AppView.vue"),
      meta: { mode: "review" },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/AdminView.vue"),
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/today",
    },
  ],
});

export default router;
