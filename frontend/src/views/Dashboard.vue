<template>
  <section class="dashboard">
    <el-skeleton :loading="loading" animated>
      <template #template>
        <div class="dashboard__grid">
          <div v-for="item in 5" :key="item" class="metric-card metric-card--skeleton">
            <div class="metric-card__header">
              <el-skeleton-item class="metric-card__icon-skeleton" variant="circle" />
              <el-skeleton-item style="width: 76px; height: 16px" variant="text" />
            </div>
            <el-skeleton-item style="width: 112px; height: 32px" variant="text" />
            <el-skeleton-item style="width: 128px; height: 14px" variant="text" />
          </div>
        </div>
      </template>

      <div class="dashboard__grid">
        <el-card
          v-for="card in cards"
          :key="card.label"
          :body-style="{ padding: '0' }"
          :class="['metric-card', { 'metric-card--alert': card.alert }]"
          shadow="hover"
        >
          <div class="metric-card__content">
            <div class="metric-card__header">
              <div :class="['metric-card__icon', `metric-card__icon--${card.tone}`]">
                <el-icon size="20">
                  <component :is="card.icon" />
                </el-icon>
              </div>
              <span class="metric-card__label">{{ card.label }}</span>
            </div>
            <strong :class="['metric-card__value', `metric-card__value--${card.tone}`]">
              {{ card.value }}
            </strong>
            <span :class="['metric-card__meta', { 'metric-card__meta--alert': card.alert }]">
              {{ card.meta }}
            </span>
          </div>
        </el-card>
      </div>
    </el-skeleton>

    <section class="dashboard__trend">
      <span>消息趋势图 - 待接入</span>
    </section>
  </section>
</template>

<script setup lang="ts">
import {
  Clock,
  Connection,
  Promotion,
  User,
  WarningFilled,
} from '@element-plus/icons-vue';
import { computed, onMounted, ref } from 'vue';
import type { Component } from 'vue';

import { fetchDashboardSummary } from '@/api/dashboard';
import type { DashboardSummary } from '@/types/dashboard';

interface MetricCard {
  label: string;
  value: string;
  meta: string;
  tone: 'blue' | 'green' | 'orange' | 'violet' | 'red';
  icon: Component;
  alert: boolean;
}

const defaultSummary: DashboardSummary = {
  todayServedCount: 0,
  aiReplyRate: 0,
  escalationCount: 0,
  avgFirstResponseMs: 0,
  unrepliedCount: 0,
  yesterdayServedCount: 0,
};

const loading = ref(true);
const summary = ref<DashboardSummary>(defaultSummary);

const cards = computed<MetricCard[]>(() => {
  const compareRate =
    summary.value.yesterdayServedCount > 0
      ? ((summary.value.todayServedCount - summary.value.yesterdayServedCount) /
          summary.value.yesterdayServedCount) *
        100
      : null;

  return [
    {
      label: '今日接待人数',
      value: formatCount(summary.value.todayServedCount),
      meta: compareRate === null ? '较昨日 --' : `较昨日 ${formatDelta(compareRate)}`,
      tone: 'blue',
      icon: User,
      alert: false,
    },
    {
      label: 'AI 自动回复率',
      value: formatRate(summary.value.aiReplyRate),
      meta: '目标保持在 90% 以上',
      tone: 'green',
      icon: Connection,
      alert: false,
    },
    {
      label: '转人工次数',
      value: formatCount(summary.value.escalationCount),
      meta: '重点关注高频转人工会话',
      tone: 'orange',
      icon: Promotion,
      alert: false,
    },
    {
      label: '平均首次响应时长',
      value: formatDuration(summary.value.avgFirstResponseMs),
      meta: '响应越快，转化越稳',
      tone: 'violet',
      icon: Clock,
      alert: false,
    },
    {
      label: '未回复会话',
      value: formatCount(summary.value.unrepliedCount),
      meta: summary.value.unrepliedCount > 0 ? '存在待处理会话，请及时跟进' : '当前无待回复积压',
      tone: 'red',
      icon: WarningFilled,
      alert: summary.value.unrepliedCount > 0,
    },
  ];
});

onMounted(async () => {
  try {
    summary.value = await fetchDashboardSummary();
  } finally {
    loading.value = false;
  }
});

function formatCount(value: number): string {
  return value.toLocaleString('zh-CN');
}

function formatRate(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatDuration(value: number): string {
  return `${(value / 1000).toFixed(1)}s`;
}

function formatDelta(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}
</script>

<style scoped>
.dashboard {
  display: grid;
  gap: 20px;
}

.dashboard__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  border: 1px solid rgba(99, 123, 160, 0.16);
  border-radius: 24px;
  background: #fff;
  box-shadow: 0 18px 42px rgba(17, 38, 66, 0.08);
}

.metric-card :deep(.el-card__body) {
  height: 100%;
}

.metric-card--alert {
  border-color: rgba(217, 83, 79, 0.42);
  box-shadow: 0 18px 42px rgba(217, 83, 79, 0.14);
}

.metric-card__content {
  display: grid;
  gap: 18px;
  min-height: 184px;
  padding: 22px;
}

.metric-card__header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.metric-card__icon,
.metric-card__icon-skeleton {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 999px;
}

.metric-card__icon--blue {
  color: #1967d2;
  background: rgba(25, 103, 210, 0.12);
}

.metric-card__icon--green {
  color: #169b62;
  background: rgba(22, 155, 98, 0.12);
}

.metric-card__icon--orange {
  color: #d97706;
  background: rgba(217, 119, 6, 0.12);
}

.metric-card__icon--violet {
  color: #6d4aff;
  background: rgba(109, 74, 255, 0.12);
}

.metric-card__icon--red {
  color: #d9485f;
  background: rgba(217, 72, 95, 0.12);
}

.metric-card__label {
  color: #6d7f95;
  font-size: 14px;
}

.metric-card__value {
  font-size: 31px;
  font-weight: 700;
  line-height: 1;
  color: #152238;
}

.metric-card__value--green {
  color: #169b62;
}

.metric-card__value--orange {
  color: #d97706;
}

.metric-card__value--violet {
  color: #6d4aff;
}

.metric-card__value--red {
  color: #d9485f;
}

.metric-card__meta {
  color: #7a889a;
  font-size: 14px;
  line-height: 1.5;
}

.metric-card__meta--alert {
  color: #c43d50;
}

.metric-card--skeleton {
  padding: 22px;
}

.dashboard__trend {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  border: 1px dashed rgba(116, 136, 168, 0.38);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.68);
  color: #61748d;
  font-size: 16px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

@media (max-width: 1280px) {
  .dashboard__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 880px) {
  .dashboard__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .dashboard__grid {
    grid-template-columns: 1fr;
  }

  .metric-card__content {
    min-height: 160px;
  }
}
</style>
