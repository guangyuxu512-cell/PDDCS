<template>
  <section class="chat-monitor">
    <aside class="chat-monitor__sidebar">
      <div class="chat-monitor__filters">
        <el-select v-model="shopFilter" placeholder="全部店铺">
          <el-option label="全部店铺" value="all" />
          <el-option
            v-for="option in shopOptions"
            :key="option.shopId"
            :label="option.shopName"
            :value="option.shopId"
          />
        </el-select>
        <el-select v-model="statusFilter" placeholder="全部状态">
          <el-option label="全部状态" value="all" />
          <el-option
            v-for="option in statusOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>

      <el-scrollbar class="chat-monitor__session-scroll">
        <div class="chat-monitor__session-list">
          <button
            v-for="session in filteredSessions"
            :key="session.id"
            :class="[
              'chat-monitor__session-item',
              { 'chat-monitor__session-item--active': session.id === selectedSession?.id },
            ]"
            type="button"
            @click="selectedSessionId = session.id"
          >
            <div class="chat-monitor__session-head">
              <strong>{{ session.buyerName }}</strong>
              <span>{{ formatTime(session.updatedAt) }}</span>
            </div>
            <p>{{ session.lastMessagePreview }}</p>
            <el-tag :type="statusTagType(session.status)" effect="light" round size="small">
              {{ chatStatusLabel[session.status] }}
            </el-tag>
          </button>
        </div>
      </el-scrollbar>
    </aside>

    <section class="chat-monitor__detail">
      <template v-if="selectedSession">
        <header class="chat-monitor__detail-header">
          <div>
            <h3>{{ selectedSession.buyerName }}</h3>
            <div class="chat-monitor__detail-meta">
              <span>{{ selectedSession.shopName }}</span>
              <el-tag :type="platformTagType(selectedSession.platform)" effect="light" round>
                {{ platformLabel[selectedSession.platform] }}
              </el-tag>
              <el-tag :type="statusTagType(selectedSession.status)" effect="light" round>
                {{ chatStatusLabel[selectedSession.status] }}
              </el-tag>
            </div>
          </div>
        </header>

        <el-scrollbar class="chat-monitor__messages">
          <div class="chat-monitor__message-list">
            <article
              v-for="message in selectedSession.messages"
              :key="message.id"
              :class="['chat-monitor__message', `chat-monitor__message--${message.sender}`]"
            >
              <div class="chat-monitor__bubble">
                <span>{{ message.content }}</span>
                <time>{{ formatTime(message.createdAt) }}</time>
              </div>
            </article>
          </div>
        </el-scrollbar>

        <footer class="chat-monitor__footer">
          <el-button
            :disabled="selectedSession.status === 'escalated'"
            type="primary"
            @click="handleTakeover"
          >
            接管此会话
          </el-button>
        </footer>
      </template>
      <el-empty v-else description="没有匹配的会话" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, onMounted, ref } from 'vue';

import { fetchChatSessions, takeoverChatSession } from '@/api/chat';
import { chatStatusLabel, type ChatSession, type ChatSessionStatus } from '@/types/chat';
import { platformLabel, type Platform } from '@/types/shop';

type StatusFilter = 'all' | ChatSessionStatus;

const sessions = ref<ChatSession[]>([]);
const selectedSessionId = ref<string>('');
const shopFilter = ref<string>('all');
const statusFilter = ref<StatusFilter>('all');

const statusOptions: Array<{ label: string; value: ChatSessionStatus }> = [
  { label: 'AI处理中', value: 'ai_processing' },
  { label: '已转人工', value: 'escalated' },
  { label: '已结束', value: 'closed' },
];

const shopOptions = computed(() =>
  Array.from(new Map(sessions.value.map((session) => [session.shopId, session])).values()).map(
    (session) => ({
      shopId: session.shopId,
      shopName: session.shopName,
    }),
  ),
);

const filteredSessions = computed(() =>
  sessions.value.filter((session) => {
    const matchShop = shopFilter.value === 'all' || session.shopId === shopFilter.value;
    const matchStatus = statusFilter.value === 'all' || session.status === statusFilter.value;
    return matchShop && matchStatus;
  }),
);

const selectedSession = computed(() => {
  const exact = filteredSessions.value.find((session) => session.id === selectedSessionId.value);
  return exact ?? filteredSessions.value[0] ?? null;
});

onMounted(async () => {
  try {
    sessions.value = await fetchChatSessions();
    selectedSessionId.value = sessions.value[0]?.id ?? '';
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '会话列表加载失败');
  }
});

async function handleTakeover(): Promise<void> {
  if (!selectedSession.value) {
    return;
  }

  try {
    const updated = await takeoverChatSession(selectedSession.value.id);
    sessions.value = sessions.value.map((session) => (session.id === updated.id ? updated : session));
    selectedSessionId.value = updated.id;
    ElMessage.success('会话已转由人工接管');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '接管会话失败');
  }
}

function statusTagType(status: ChatSessionStatus): 'primary' | 'warning' | 'info' {
  switch (status) {
    case 'ai_processing':
      return 'primary';
    case 'escalated':
      return 'warning';
    case 'closed':
      return 'info';
  }
}

function platformTagType(platform: Platform): 'warning' | 'primary' | 'danger' {
  switch (platform) {
    case 'pdd':
      return 'warning';
    case 'douyin':
      return 'primary';
    case 'qianniu':
      return 'danger';
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
</script>

<style scoped>
.chat-monitor {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
  min-height: 700px;
}

.chat-monitor__sidebar,
.chat-monitor__detail {
  display: grid;
  gap: 14px;
  padding: 20px;
  border: 1px solid rgba(99, 123, 160, 0.18);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 48px rgba(17, 38, 66, 0.08);
}

.chat-monitor__sidebar {
  grid-template-rows: auto minmax(0, 1fr);
}

.chat-monitor__filters {
  display: grid;
  gap: 12px;
}

.chat-monitor__session-scroll,
.chat-monitor__messages {
  min-height: 0;
}

.chat-monitor__session-list,
.chat-monitor__message-list {
  display: grid;
  gap: 10px;
}

.chat-monitor__session-item {
  padding: 14px;
  border: 1px solid rgba(99, 123, 160, 0.14);
  border-radius: 18px;
  background: #f8fafc;
  text-align: left;
  cursor: pointer;
}

.chat-monitor__session-item--active {
  border-color: rgba(53, 117, 255, 0.34);
  background: rgba(53, 117, 255, 0.08);
}

.chat-monitor__session-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.chat-monitor__session-item strong {
  color: #152238;
}

.chat-monitor__session-item span,
.chat-monitor__session-item p {
  color: #66788e;
  font-size: 13px;
}

.chat-monitor__detail {
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.chat-monitor__detail-header h3 {
  margin: 0 0 10px;
  font-size: 26px;
  color: #16243a;
}

.chat-monitor__detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  color: #6c7f96;
}

.chat-monitor__message {
  display: flex;
}

.chat-monitor__message--buyer {
  justify-content: flex-start;
}

.chat-monitor__message--ai,
.chat-monitor__message--human {
  justify-content: flex-end;
}

.chat-monitor__bubble {
  display: grid;
  gap: 8px;
  max-width: 72%;
  padding: 14px 16px;
  border-radius: 20px;
  box-shadow: 0 10px 26px rgba(17, 38, 66, 0.08);
}

.chat-monitor__message--buyer .chat-monitor__bubble {
  background: #eef2f7;
  color: #293a4d;
}

.chat-monitor__message--ai .chat-monitor__bubble,
.chat-monitor__message--human .chat-monitor__bubble {
  background: linear-gradient(135deg, #2a73ff 0%, #4d8dff 100%);
  color: #fff;
}

.chat-monitor__bubble time {
  font-size: 12px;
  opacity: 0.8;
}

.chat-monitor__footer {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 960px) {
  .chat-monitor {
    grid-template-columns: 1fr;
  }
}
</style>
