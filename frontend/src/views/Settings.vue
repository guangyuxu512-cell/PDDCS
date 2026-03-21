<template>
  <section class="settings">
    <el-skeleton :loading="loading" animated>
      <template #template>
        <el-skeleton-item style="width: 100%; height: 360px" variant="p" />
      </template>

      <el-form class="settings__form" label-position="top">
        <el-divider content-position="left">全局 LLM 配置</el-divider>
        <div class="settings__grid">
          <el-form-item label="API Base URL">
            <el-input v-model="formState.apiBaseUrl" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="formState.apiKey" show-password />
          </el-form-item>
          <el-form-item class="settings__test-action" label="连接测试">
            <el-button :loading="testingConnection" plain type="success" @click="handleTestConnection">
              测试连接
            </el-button>
          </el-form-item>
          <el-form-item label="默认模型名称">
            <el-input v-model="formState.defaultModel" />
          </el-form-item>
          <el-form-item label="Temperature">
            <el-input-number v-model="formState.temperature" :max="2" :min="0" :step="0.1" />
          </el-form-item>
          <el-form-item label="最大 Token">
            <el-input-number v-model="formState.maxTokens" :min="1" />
          </el-form-item>
        </div>

        <el-divider content-position="left">全局转人工默认规则</el-divider>
        <div class="settings__grid">
          <el-form-item class="settings__full" label="默认兜底话术">
            <el-input v-model="formState.defaultFallbackMsg" :rows="3" type="textarea" />
          </el-form-item>
          <el-form-item class="settings__full" label="默认关键词列表">
            <el-input v-model="defaultKeywordsText" :rows="5" type="textarea" />
          </el-form-item>
          <p class="settings__hint">新店铺创建时将自动继承这些默认规则</p>
        </div>

        <el-divider content-position="left">系统配置</el-divider>
        <div class="settings__grid">
          <el-form-item label="日志级别">
            <el-select v-model="formState.logLevel">
              <el-option v-for="level in logLevels" :key="level" :label="level" :value="level" />
            </el-select>
          </el-form-item>
          <el-form-item label="会话历史保留天数">
            <el-input-number v-model="formState.historyRetentionDays" :min="1" />
          </el-form-item>
          <el-form-item label="单机最大店铺数">
            <el-input-number v-model="formState.maxShops" :min="1" />
          </el-form-item>
        </div>

        <el-divider content-position="left">通知配置</el-divider>
        <div class="settings__grid">
          <el-form-item label="Webhook 类型">
            <el-select v-model="formState.notifyWebhookType">
              <el-option
                v-for="item in webhookTypes"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item class="settings__test-action" label="发送测试">
            <el-button :loading="testingWebhook" plain type="warning" @click="handleTestWebhook">
              测试通知
            </el-button>
          </el-form-item>
          <el-form-item class="settings__full" label="Webhook URL">
            <el-input
              v-model="formState.notifyWebhookUrl"
              clearable
              placeholder="请输入飞书/钉钉/企微机器人 Webhook URL"
            />
          </el-form-item>
        </div>

        <div class="settings__footer">
          <el-button :loading="saving" type="primary" @click="handleSave">保存</el-button>
        </div>
      </el-form>
    </el-skeleton>
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { onMounted, ref } from 'vue';

import { fetchSettings, saveSettings, testLlmConnection, testWebhook } from '@/api/settings';
import type { LogLevel, SystemSettings, WebhookType } from '@/types/settings';

const loading = ref(true);
const saving = ref(false);
const testingConnection = ref(false);
const testingWebhook = ref(false);
const defaultKeywordsText = ref('');
const formState = ref<SystemSettings>({
  apiBaseUrl: '',
  apiKey: '',
  defaultModel: '',
  temperature: 0.7,
  maxTokens: 200,
  defaultFallbackMsg: '',
  defaultKeywords: [],
  logLevel: 'INFO',
  historyRetentionDays: 30,
  notifyWebhookUrl: '',
  notifyWebhookType: 'feishu',
  maxShops: 10,
});

const logLevels: LogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];
const webhookTypes: Array<{ label: string; value: WebhookType }> = [
  { label: '飞书', value: 'feishu' },
  { label: '钉钉', value: 'dingtalk' },
  { label: '企业微信', value: 'wecom' },
  { label: '通用', value: 'generic' },
];

onMounted(async () => {
  try {
    const settings = await fetchSettings();
    formState.value = settings;
    defaultKeywordsText.value = settings.defaultKeywords.join('\n');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '系统设置加载失败');
  } finally {
    loading.value = false;
  }
});

async function handleSave(): Promise<void> {
  saving.value = true;
  try {
    const payload: SystemSettings = {
      ...formState.value,
      defaultKeywords: defaultKeywordsText.value
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    };
    const saved = await saveSettings(payload);
    formState.value = saved;
    defaultKeywordsText.value = saved.defaultKeywords.join('\n');
    ElMessage.success('系统设置已保存');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '系统设置保存失败');
  } finally {
    saving.value = false;
  }
}

async function handleTestConnection(): Promise<void> {
  if (!formState.value.apiBaseUrl.trim() || !formState.value.apiKey.trim() || !formState.value.defaultModel.trim()) {
    ElMessage.error('请先填写 API Base URL、API Key 和默认模型名称');
    return;
  }

  testingConnection.value = true;
  try {
    await testLlmConnection({
      apiBaseUrl: formState.value.apiBaseUrl.trim(),
      apiKey: formState.value.apiKey.trim(),
      model: formState.value.defaultModel.trim(),
    });
    ElMessage.success('LLM 连接测试成功，模型响应正常');
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    ElMessage.error(`连接失败: ${message}`);
  } finally {
    testingConnection.value = false;
  }
}

async function handleTestWebhook(): Promise<void> {
  if (!formState.value.notifyWebhookUrl.trim()) {
    ElMessage.error('请先填写 Webhook URL');
    return;
  }

  testingWebhook.value = true;
  try {
    const result = await testWebhook({
      url: formState.value.notifyWebhookUrl.trim(),
      webhookType: formState.value.notifyWebhookType,
    });
    if (result.ok) {
      ElMessage.success(result.message || '发送成功');
      return;
    }
    ElMessage.error(result.message || '发送失败');
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    ElMessage.error(`发送失败: ${message}`);
  } finally {
    testingWebhook.value = false;
  }
}
</script>

<style scoped>
.settings {
  padding: 24px;
  border: 1px solid rgba(99, 123, 160, 0.18);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 48px rgba(17, 38, 66, 0.08);
}

.settings__form {
  display: grid;
  gap: 12px;
}

.settings__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.settings__full,
.settings__hint {
  grid-column: 1 / -1;
}

.settings__test-action {
  align-self: end;
}

.settings__hint {
  margin: 0;
  color: #677a92;
  font-size: 14px;
}

.settings__footer {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 860px) {
  .settings {
    padding: 18px 16px;
  }

  .settings__grid {
    grid-template-columns: 1fr;
  }
}
</style>
