<template>
  <header class="topbar">
    <div>
      <p class="topbar__label">Step 1</p>
      <h2>{{ currentTitle }}</h2>
    </div>

    <div class="topbar__actions">
      <span class="topbar__switch-label">全局 AI</span>
      <el-switch
        v-model="aiEnabled"
        inline-prompt
        active-text="开"
        inactive-text="关"
        @change="handleAiToggle"
      />
      <el-badge :value="3" class="topbar__badge">
        <el-button circle :icon="Bell" @click="showNotifications" />
      </el-badge>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Bell } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();
const aiEnabled = ref(true);

const currentTitle = computed(() => route.meta.title ?? '总览');

function handleAiToggle(value: string | number | boolean): void {
  ElMessage.success(value ? '全局 AI 已开启' : '全局 AI 已关闭');
}

function showNotifications(): void {
  ElMessage.info('这里将在后续步骤接入系统通知和告警。');
}
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 10px;
}

.topbar h2 {
  margin: 6px 0 0;
  font-size: 28px;
  color: #152238;
}

.topbar__label {
  margin: 0;
  color: #5d7698;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.topbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topbar__switch-label {
  color: #415872;
  font-weight: 600;
}

.topbar__badge :deep(.el-badge__content) {
  border: 0;
}

@media (max-width: 960px) {
  .topbar {
    flex-direction: column;
    align-items: flex-start;
    padding: 18px 16px 10px;
  }
}
</style>
