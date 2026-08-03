<script setup lang="ts">
// 用户档案面板：目标岗位、JD、头像、提醒偏好与长期训练记忆管理。
import { computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useProfileStore } from "@/stores/profile";
import { formatProfileDate } from "@/lib/format";
import { escapeText } from "@/lib/markdown";

const store = useProfileStore();
const router = useRouter();

async function load() {
  await store.load();
}

function selectTopic(topic: string) {
  store.setTopic(topic || null);
}

onMounted(load);
watch(() => store.selectedTopic, load);

// 趋势图 SVG(从旧 renderTrendChart 迁移,改为计算属性)
const trendChart = computed(() => {
  const trend = store.data?.trend ?? [];
  if (!trend.length) return null;
  const width = 720;
  const height = 190;
  const paddingX = 34;
  const paddingY = 24;
  const plotWidth = width - paddingX * 2;
  const plotHeight = height - paddingY * 2;
  const points = trend.map((item, index) => {
    const x =
      trend.length === 1 ? width / 2 : paddingX + (plotWidth * index) / (trend.length - 1);
    const score = Math.max(0, Math.min(10, Number(item.average_score)));
    const y = paddingY + plotHeight * (1 - score / 10);
    return { x, y, score, item };
  });
  const polyline = points.map(({ x, y }) => `${x},${y}`).join(" ");
  const guides = [0, 5, 10]
    .map((score) => {
      const y = paddingY + plotHeight * (1 - score / 10);
      return `
        <line x1="${paddingX}" y1="${y}" x2="${width - paddingX}" y2="${y}" />
        <text x="3" y="${y + 4}">${score}</text>
      `;
    })
    .join("");
  const markers = points
    .map(
      ({ x, y, score, item }) => `
    <g>
      <circle cx="${x}" cy="${y}" r="5" />
      <text class="trend-score" x="${x}" y="${y - 11}" text-anchor="middle">${score}</text>
      <text x="${x}" y="${height - 3}" text-anchor="middle">${escapeText(formatProfileDate(item.updated_at))}</text>
    </g>
  `,
    )
    .join("");
  return { width, height, polyline, guides, markers };
});

const improvementLabel = computed(() => {
  const imp = Number(store.data?.summary.improvement ?? 0);
  return imp > 0 ? `+${imp}` : String(imp);
});
</script>

<template>
  <section class="learning-panel">
    <div class="interview-card profile-card">
      <div v-if="store.loading" class="list-state">正在汇总跨场次能力画像…</div>
      <div v-else-if="store.error" class="list-state error">
        {{ store.error }}
        <button class="retry-link" @click="load()">重试</button>
      </div>
      <template v-else-if="store.data">
        <div class="profile-heading">
          <div>
            <span class="eyebrow">能力画像</span>
            <h2>跨场次能力画像</h2>
          </div>
          <label>
            主题筛选
            <select
              :value="store.selectedTopic || ''"
              @change="selectTopic(($event.target as HTMLSelectElement).value)"
            >
              <option value="">全部主题</option>
              <option
                v-for="topic in store.data.available_topics"
                :key="topic"
                :value="topic"
              >
                {{ topic }}
              </option>
            </select>
          </label>
        </div>

        <template v-if="!store.data.summary.answered_questions">
          <div class="profile-empty profile-empty-large">
            <strong>
              {{ store.selectedTopic ? "该主题暂无评分数据" : "还没有可聚合的面试评分" }}
            </strong>
            <span>完成至少一道模拟面试题后,系统会自动生成趋势和薄弱点。</span>
          </div>
        </template>

        <template v-else>
          <div class="profile-summary">
            <div>
              <span>综合得分</span>
              <strong>{{ store.data.summary.average_score }}</strong>
              <small>/ 10</small>
            </div>
            <div>
              <span>训练场次</span>
              <strong>{{ store.data.summary.interviews }}</strong>
              <small>{{ store.data.summary.completed_interviews }} 场已完成</small>
            </div>
            <div>
              <span>已答题目</span>
              <strong>{{ store.data.summary.answered_questions }}</strong>
              <small>累计评分</small>
            </div>
            <div>
              <span>首尾变化</span>
              <strong :class="Number(store.data.summary.improvement) < 0 ? 'score-down' : 'score-up'">
                {{ improvementLabel }}
              </strong>
              <small>场均分</small>
            </div>
          </div>
          <p class="profile-confidence">
            当前画像基于 {{ store.data.summary.answered_questions }} 道已评分回答。
            {{ store.data.summary.answered_questions < 10 ? "样本仍较少，建议继续完成至少 10 道题后再判断长期趋势。" : "样本量已可用于观察阶段性变化。" }}
          </p>

          <section class="profile-section job-readiness">
            <div class="section-heading">
              <h3>目标岗位准备度</h3>
              <span>
                置信度：
                {{
                  store.data.job_readiness.confidence === "high"
                    ? "高"
                    : store.data.job_readiness.confidence === "medium"
                      ? "中"
                      : "低"
                }}
              </span>
            </div>
            <div class="readiness-score">
              <strong>{{ store.data.job_readiness.score }}</strong><small>/ 100</small>
              <span>{{ store.data.job_readiness.target_role || "尚未设置目标岗位" }}</span>
            </div>
            <ol v-if="store.data.job_readiness.priorities.length" class="weakness-list">
              <li
                v-for="(priority, i) in store.data.job_readiness.priorities"
                :key="priority.label"
              >
                <span>{{ i + 1 }}</span>
                <strong>{{ priority.label }}</strong>
                <b>{{ priority.reason }}</b>
              </li>
            </ol>
            <p class="profile-confidence">
              {{
                store.data.job_readiness.has_job_description
                  ? "已结合目标 JD；准备度会随训练样本增加而提高可信度。"
                  : "补充目标 JD 后，可获得更贴近岗位要求的优先级建议。"
              }}
            </p>
          </section>

          <section class="profile-section">
            <div class="section-heading">
              <h3>四维能力</h3>
              <span>全部已评分题目的平均值</span>
            </div>
            <div class="dimension-profile-grid">
              <div
                v-for="[name, score] in Object.entries(store.data.dimension_scores)"
                :key="name"
                class="dimension-profile"
              >
                <div><span>{{ name }}</span><strong>{{ score }}</strong></div>
                <div class="score-track">
                  <i :style="{ width: `${Math.max(0, Math.min(100, Number(score) * 10))}%` }"></i>
                </div>
              </div>
            </div>
          </section>

          <section class="profile-section">
            <div class="section-heading">
              <h3>分数趋势</h3>
              <span>按面试更新时间排列</span>
            </div>
            <div v-if="trendChart" v-html="`
              <svg class='trend-chart' viewBox='0 0 ${trendChart.width} ${trendChart.height}' role='img' aria-label='面试平均分趋势'>
                <g class='trend-guides'>${trendChart.guides}</g>
                <polyline points='${trendChart.polyline}' />
                <g class='trend-markers'>${trendChart.markers}</g>
              </svg>
            `"></div>
            <div v-else class="profile-empty">完成模拟面试后,这里会显示分数趋势。</div>
          </section>

          <div class="profile-columns">
            <section class="profile-section">
              <div class="section-heading"><h3>主题表现</h3><span>点击可筛选</span></div>
              <div class="topic-breakdown">
                <button
                  v-for="item in store.data.topic_breakdown"
                  :key="item.topic"
                  class="topic-row"
                  type="button"
                  @click="selectTopic(item.topic)"
                >
                  <span>
                    <strong>{{ item.topic }}</strong>
                    <small>{{ item.interviews }} 场 · {{ item.answered_questions }} 题</small>
                  </span>
                  <b>{{ item.average_score }}</b>
                </button>
                <div v-if="!store.data.topic_breakdown.length" class="profile-empty">暂无主题数据</div>
              </div>
            </section>

            <section class="profile-section">
              <div class="section-heading">
                <h3>主要薄弱点</h3>
                <button class="text-action" type="button" @click="router.push('/learning')">
                  生成专项计划
                </button>
              </div>
              <ol class="weakness-list">
                <li v-for="(item, i) in store.data.weaknesses" :key="i">
                  <span>{{ i + 1 }}</span>
                  <strong>{{ item.label }}</strong>
                  <b>{{ item.count }} 次</b>
                </li>
                <li v-if="!store.data.weaknesses.length" class="muted-list-item">
                  继续训练后生成薄弱点
                </li>
              </ol>
            </section>
          </div>

          <div class="profile-columns">
            <section class="profile-section">
              <div class="section-heading"><h3>最近训练</h3><span>最近 5 场</span></div>
              <ul class="recent-training">
                <li v-for="(item, i) in store.data.recent_training" :key="i">
                  <span class="recent-score">{{ item.average_score }}</span>
                  <span>
                    <strong>{{ item.topic }}</strong>
                    <small>{{ item.level }} · {{ item.answered_questions }} 题 · {{ formatProfileDate(item.updated_at) }}</small>
                  </span>
                </li>
              </ul>
            </section>

            <section class="profile-section">
              <div class="section-heading"><h3>高频问题</h3><span>相同题目统计</span></div>
              <ul class="frequent-questions">
                <li v-for="(item, i) in store.data.frequent_questions" :key="i">
                  <span>{{ item.question }}</span>
                  <b>{{ item.count }} 次</b>
                </li>
                <li v-if="!store.data.frequent_questions.length">
                  <span>完成更多面试后生成题目统计</span>
                </li>
              </ul>
            </section>
          </div>
        </template>
      </template>
    </div>
  </section>
</template>
