// 应用入口：创建 Vue 实例、挂载 Pinia/路由并初始化前端可观测性。
import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";

// 高亮代码主题(打包进产物,满足 CSP)
import "highlight.js/styles/github-dark.css";
// Phosphor 图标(本地精简版,仅 woff2;打包进产物满足 CSP;全项目统一 regular weight)
import "./styles/phosphor.css";

import "./styles/base.css";
import "./styles/app.css";
import "./styles/components.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
