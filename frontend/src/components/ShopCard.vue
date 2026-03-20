<template>
  <el-card class="shop-card" shadow="hover">
    <div class="shop-card__content">
      <div class="shop-card__header">
        <div>
          <h3>{{ shop.name }}</h3>
          <div class="shop-card__meta">
            <el-tag :type="platformTagType" effect="light" round>
              {{ platformLabel[shop.platform] }}
            </el-tag>
            <span class="shop-card__status">
              <i :class="['shop-card__status-dot', { 'shop-card__status-dot--online': shop.isOnline }]"></i>
              {{ shop.isOnline ? '在线' : '离线' }}
            </span>
          </div>
        </div>
        <el-switch
          :model-value="shop.aiEnabled"
          inline-prompt
          active-text="AI"
          inactive-text="关"
          @change="handleAiToggle"
        />
      </div>

      <dl class="shop-card__stats">
        <div>
          <dt>今日接待数</dt>
          <dd>{{ shop.todayServedCount }}</dd>
        </div>
        <div>
          <dt>最近活跃</dt>
          <dd>{{ lastActiveText }}</dd>
        </div>
      </dl>

      <div class="shop-card__actions">
        <el-tooltip content="打开客服后台" placement="top">
          <el-button circle plain @click="emit('open-browser', shop.id)">
            <el-icon><Monitor /></el-icon>
          </el-button>
        </el-tooltip>
        <el-button plain @click="emit('edit', shop.id)">编辑</el-button>
        <el-popconfirm title="确认删除该店铺吗？" @confirm="emit('delete', shop.id)">
          <template #reference>
            <el-button plain type="danger">删除</el-button>
          </template>
        </el-popconfirm>
        <el-button :type="shop.isOnline ? 'danger' : 'primary'" @click="emit('toggleStatus', shop.id)">
          {{ shop.isOnline ? '停止' : '启动' }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { Monitor } from '@element-plus/icons-vue';
import { computed } from 'vue';

import { platformLabel, type Shop } from '@/types/shop';

const props = defineProps<{
  shop: Shop;
}>();

const emit = defineEmits<{
  delete: [shopId: string];
  edit: [shopId: string];
  'open-browser': [shopId: string];
  toggleAi: [shopId: string, enabled: boolean];
  toggleStatus: [shopId: string];
}>();

const platformTagType = computed(() => {
  switch (props.shop.platform) {
    case 'pdd':
      return 'warning';
    case 'douyin':
      return 'primary';
    case 'qianniu':
      return 'danger';
  }
});

const lastActiveText = computed(() => {
  if (!props.shop.lastActiveAt) {
    return '暂无';
  }

  return new Date(props.shop.lastActiveAt).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
});

function handleAiToggle(value: string | number | boolean): void {
  emit('toggleAi', props.shop.id, Boolean(value));
}
</script>

<style scoped>
.shop-card {
  border: 1px solid rgba(99, 123, 160, 0.16);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 42px rgba(17, 38, 66, 0.08);
}

.shop-card__content {
  display: grid;
  gap: 18px;
}

.shop-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.shop-card__header h3 {
  margin: 0;
  font-size: 22px;
  color: #16243a;
}

.shop-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.shop-card__status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #5d6f86;
  font-size: 14px;
}

.shop-card__status-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #b3bfce;
}

.shop-card__status-dot--online {
  background: #28b66f;
  box-shadow: 0 0 0 4px rgba(40, 182, 111, 0.12);
}

.shop-card__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}

.shop-card__stats div {
  padding: 14px;
  border-radius: 18px;
  background: #f6f8fb;
}

.shop-card__stats dt {
  color: #6e7f95;
  font-size: 13px;
}

.shop-card__stats dd {
  margin: 8px 0 0;
  color: #152238;
  font-size: 20px;
  font-weight: 700;
}

.shop-card__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 640px) {
  .shop-card__header,
  .shop-card__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .shop-card__stats {
    grid-template-columns: 1fr;
  }
}
</style>
