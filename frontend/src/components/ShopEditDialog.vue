<template>
  <el-dialog v-model="dialogVisible" title="编辑店铺" width="680px" destroy-on-close>
    <el-skeleton :loading="loading" animated>
      <template #template>
        <el-skeleton-item style="width: 100%; height: 260px" variant="p" />
      </template>

      <el-collapse v-model="activePanels" class="shop-edit-dialog__collapse">
        <el-collapse-item name="basic" title="基础信息">
          <div class="shop-edit-dialog__grid">
            <label class="shop-edit-dialog__field">
              <span>店铺名称</span>
              <el-input v-model="formState.name" placeholder="请输入店铺名称" />
            </label>
            <label class="shop-edit-dialog__field">
              <span>所属平台</span>
              <el-select v-model="formState.platform" :disabled="Boolean(shopId)" placeholder="请选择平台">
                <el-option
                  v-for="platform in platformOptions"
                  :key="platform.value"
                  :label="platform.label"
                  :value="platform.value"
                />
              </el-select>
            </label>
            <label class="shop-edit-dialog__field">
              <span>店铺账号</span>
              <el-input v-model="formState.username" placeholder="请输入店铺登录账号" />
            </label>
            <label class="shop-edit-dialog__field">
              <span>店铺密码</span>
              <el-input
                v-model="formState.password"
                placeholder="已有密码可以留空不更新"
                show-password
              />
              <small class="shop-edit-dialog__field-note">
                {{ formState.hasPassword ? '已配置密码，留空则保持不变' : '当前未配置密码，保存前必须填写' }}
              </small>
            </label>
            <div class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>Cookie 状态</span>
              <div class="shop-edit-dialog__cookie">
                <el-tag :type="formState.cookieValid ? 'success' : 'danger'" round>
                  {{ formState.cookieValid ? '有效' : '已过期' }}
                </el-tag>
                <span>Cookie 指纹：{{ cookieFingerprintText }}</span>
              </div>
            </div>
            <div class="shop-edit-dialog__field">
              <span>自动重启</span>
              <div>
                <el-switch
                  v-model="formState.autoRestart"
                  inline-prompt
                  active-text="开"
                  inactive-text="关"
                />
                <div class="shop-edit-dialog__field-note">浏览器关闭后自动重新打开并登录</div>
              </div>
            </div>
            <div class="shop-edit-dialog__field">
              <span>强制在线</span>
              <div>
                <el-switch
                  v-model="formState.forceOnline"
                  inline-prompt
                  active-text="开"
                  inactive-text="关"
                />
                <div class="shop-edit-dialog__field-note">定时检测客服在线状态并自动切回</div>
              </div>
            </div>
          </div>
        </el-collapse-item>

        <el-collapse-item name="ai" title="AI 配置">
          <div class="shop-edit-dialog__grid">
            <div class="shop-edit-dialog__field">
              <span>AI 开关</span>
              <el-switch v-model="formState.aiEnabled" inline-prompt active-text="开" inactive-text="关" />
            </div>
            <label class="shop-edit-dialog__field">
              <span>LLM 模式</span>
              <el-select v-model="formState.llmMode">
                <el-option label="使用全局默认" value="global" />
                <el-option label="自定义" value="custom" />
              </el-select>
            </label>
            <label v-if="formState.llmMode === 'custom'" class="shop-edit-dialog__field">
              <span>自定义 API Key</span>
              <el-input v-model="formState.customApiKey" placeholder="请输入 API Key" show-password />
            </label>
            <label v-if="formState.llmMode === 'custom'" class="shop-edit-dialog__field">
              <span>自定义模型名称</span>
              <el-input v-model="formState.customModel" placeholder="请输入模型名称" />
            </label>
            <div v-if="formState.llmMode === 'custom'" class="shop-edit-dialog__field">
              <span>连接测试</span>
              <el-button
                :loading="testingCustomConnection"
                plain
                type="success"
                @click="handleTestCustomConnection"
              >
                测试连接
              </el-button>
            </div>
            <label class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>回复风格备注</span>
              <el-input
                v-model="formState.replyStyleNote"
                :rows="3"
                placeholder="例如：语气亲切、回复简洁、少用表情"
                type="textarea"
              />
            </label>
          </div>
        </el-collapse-item>

        <el-collapse-item name="knowledge" title="知识库绑定">
          <div class="shop-edit-dialog__grid">
            <div class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>绑定知识库文件</span>
              <el-skeleton :loading="knowledgeLoading" animated>
                <template #template>
                  <el-skeleton-item style="width: 100%; height: 90px" variant="p" />
                </template>
                <el-checkbox-group v-model="formState.knowledgePaths" class="shop-edit-dialog__knowledge-list">
                  <el-checkbox
                    v-for="path in knowledgeFileOptions"
                    :key="path"
                    :label="path"
                    :value="path"
                  >
                    {{ path }}
                  </el-checkbox>
                </el-checkbox-group>
              </el-skeleton>
            </div>
            <div class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>知识库使用策略</span>
              <el-checkbox v-model="formState.useGlobalKnowledge">同时使用全局知识库</el-checkbox>
            </div>
          </div>
        </el-collapse-item>

        <el-collapse-item name="escalation" title="转人工规则">
          <div class="shop-edit-dialog__grid">
            <label class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>人工客服账号名</span>
              <el-input v-model="formState.humanAgentName" placeholder="请输入转接目标客服名称" />
            </label>

            <div class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>转人工触发规则列表</span>
              <div class="shop-edit-dialog__rules">
                <div v-for="rule in formState.escalationRules" :key="rule.id" class="shop-edit-dialog__rule-row">
                  <el-select v-model="rule.type" class="shop-edit-dialog__rule-type">
                    <el-option
                      v-for="option in ruleTypeOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                  <el-input v-model="rule.value" :placeholder="rulePlaceholderMap[rule.type]" />
                  <el-button plain type="danger" @click="removeRule(rule.id)">删除</el-button>
                </div>
              </div>
              <el-button plain type="primary" @click="addRule">添加规则</el-button>
            </div>

            <label class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>兜底话术</span>
              <el-input
                v-model="formState.escalationFallbackMsg"
                :rows="3"
                placeholder="例如：亲，已为您转接人工客服，请稍等"
                type="textarea"
              />
            </label>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-skeleton>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button :loading="saving" type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, ref, watch } from 'vue';

import { fetchKnowledgeFileList } from '@/api/knowledge';
import { testLlmConnection } from '@/api/settings';
import { fetchShopConfig, saveShopConfig } from '@/api/shopConfig';
import { platformLabel, type Platform } from '@/types/shop';
import {
  type EscalationRule,
  type EscalationRuleType,
  type ShopConfig,
  type ShopConfigSavePayload,
} from '@/types/shopConfig';

const props = defineProps<{
  modelValue: boolean;
  shopId: string | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [config: ShopConfig];
}>();

type ShopConfigForm = ShopConfigSavePayload & {
  hasPassword: boolean;
  cookieFingerprint: string;
  password: string;
};

const platformOptions: Array<{ label: string; value: Platform }> = [
  { label: platformLabel.pdd, value: 'pdd' },
  { label: platformLabel.douyin, value: 'douyin' },
  { label: platformLabel.qianniu, value: 'qianniu' },
];

const ruleTypeOptions: Array<{ label: string; value: EscalationRuleType }> = [
  { label: '关键词匹配', value: 'keyword' },
  { label: '连续追问次数', value: 'repeat_ask' },
  { label: '订单金额阈值', value: 'order_amount' },
  { label: '正则表达式', value: 'regex' },
];

const rulePlaceholderMap: Record<EscalationRuleType, string> = {
  keyword: '例如：退款、投诉、差评',
  repeat_ask: '例如：3',
  order_amount: '例如：500',
  regex: '例如：退.*赔偿',
};

const activePanels = ref<Array<'basic' | 'ai' | 'knowledge' | 'escalation'>>([
  'basic',
  'ai',
  'knowledge',
  'escalation',
]);
const loading = ref(false);
const saving = ref(false);
const knowledgeLoading = ref(false);
const testingCustomConnection = ref(false);
const knowledgeFileOptions = ref<string[]>([]);
const formState = ref<ShopConfigForm>(createEmptyConfig());

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
});

const cookieFingerprintText = computed(() => formState.value.cookieFingerprint || '--');

watch(
  () => [props.modelValue, props.shopId] as const,
  async ([visible, shopId]) => {
    if (!visible || !shopId) {
      return;
    }

    loading.value = true;
    knowledgeLoading.value = true;
    try {
      const [config, knowledgeFiles] = await Promise.all([
        fetchShopConfig(shopId),
        fetchKnowledgeFileList(),
      ]);
      knowledgeFileOptions.value = knowledgeFiles;
      formState.value = normalizeConfig(config);
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '店铺配置加载失败');
    } finally {
      loading.value = false;
      knowledgeLoading.value = false;
    }
  },
);

function createEmptyConfig(): ShopConfigForm {
  return {
    shopId: '',
    name: '',
    username: '',
    password: '',
    platform: 'pdd',
    cookieValid: false,
    aiEnabled: false,
    hasPassword: false,
    cookieFingerprint: '',
    llmMode: 'global',
    customApiKey: '',
    customModel: '',
    replyStyleNote: '',
    knowledgePaths: [],
    useGlobalKnowledge: true,
    humanAgentName: '',
    escalationRules: [],
    escalationFallbackMsg: '',
    autoRestart: false,
    forceOnline: false,
  };
}

function normalizeConfig(config: ShopConfig): ShopConfigForm {
  return {
    ...config,
    username: config.username ?? '',
    password: '',
    hasPassword: config.hasPassword ?? false,
    cookieFingerprint: config.cookieFingerprint ?? '',
    customApiKey: config.customApiKey ?? '',
    customModel: config.customModel ?? '',
    replyStyleNote: config.replyStyleNote ?? '',
    knowledgePaths: config.knowledgePaths ?? [],
    useGlobalKnowledge: config.useGlobalKnowledge ?? true,
    autoRestart: config.autoRestart ?? false,
    forceOnline: config.forceOnline ?? false,
    escalationRules: config.escalationRules.length ? config.escalationRules : [createRule()],
  };
}

function createRule(): EscalationRule {
  return {
    id: `rule-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    type: 'keyword',
    value: '',
  };
}

function addRule(): void {
  formState.value.escalationRules.push(createRule());
}

function removeRule(ruleId: string): void {
  formState.value.escalationRules = formState.value.escalationRules.filter((rule) => rule.id !== ruleId);
}

async function handleTestCustomConnection(): Promise<void> {
  if (!formState.value.customApiKey?.trim() || !formState.value.customModel?.trim()) {
    ElMessage.error('请先填写自定义 API Key 和模型名称');
    return;
  }

  testingCustomConnection.value = true;
  try {
    await testLlmConnection({
      apiBaseUrl: '',
      apiKey: formState.value.customApiKey.trim(),
      model: formState.value.customModel.trim(),
    });
    ElMessage.success('LLM 连接测试成功，模型响应正常');
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    ElMessage.error(`连接失败: ${message}`);
  } finally {
    testingCustomConnection.value = false;
  }
}

async function handleSave(): Promise<void> {
  if (!props.shopId) {
    ElMessage.error('缺少店铺 ID，无法保存');
    return;
  }

  if (!formState.value.name.trim()) {
    ElMessage.error('店铺名称不能为空');
    return;
  }

  if (!formState.value.username.trim()) {
    ElMessage.error('店铺账号不能为空');
    return;
  }

  if (!formState.value.password.trim() && !formState.value.hasPassword) {
    ElMessage.error('店铺密码不能为空');
    return;
  }

  if (!formState.value.humanAgentName.trim()) {
    ElMessage.error('人工客服账号名不能为空');
    return;
  }

  saving.value = true;
  try {
    const savedConfig = await saveShopConfig(props.shopId, normalizeSavePayload(formState.value));
    formState.value = normalizeConfig(savedConfig);
    emit('saved', savedConfig);
    dialogVisible.value = false;
    ElMessage.success('店铺配置已保存');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '店铺配置保存失败');
  } finally {
    saving.value = false;
  }
}

function normalizeSavePayload(config: ShopConfigForm): ShopConfigSavePayload {
  const password = config.password.trim();
  return {
    shopId: props.shopId ?? config.shopId,
    name: config.name.trim(),
    username: config.username.trim(),
    platform: config.platform,
    cookieValid: config.cookieValid,
    aiEnabled: config.aiEnabled,
    llmMode: config.llmMode,
    password: password || undefined,
    customApiKey: config.llmMode === 'custom' ? config.customApiKey?.trim() ?? '' : undefined,
    customModel: config.llmMode === 'custom' ? config.customModel?.trim() ?? '' : undefined,
    replyStyleNote: config.replyStyleNote?.trim() ?? '',
    knowledgePaths: config.knowledgePaths.filter(Boolean),
    useGlobalKnowledge: config.useGlobalKnowledge,
    humanAgentName: config.humanAgentName.trim(),
    escalationRules: config.escalationRules.map((rule) => ({
      ...rule,
      value: rule.value.trim(),
    })),
    escalationFallbackMsg: config.escalationFallbackMsg.trim(),
    autoRestart: config.autoRestart,
    forceOnline: config.forceOnline,
  };
}
</script>

<style scoped>
.shop-edit-dialog__collapse {
  display: grid;
  gap: 12px;
}

.shop-edit-dialog__collapse :deep(.el-collapse-item__header) {
  font-weight: 700;
  color: #16243a;
}

.shop-edit-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.shop-edit-dialog__field {
  display: grid;
  gap: 8px;
}

.shop-edit-dialog__field span {
  color: #607289;
  font-size: 14px;
}

.shop-edit-dialog__field-note {
  margin-top: 4px;
  color: #8e9bb3;
  font-size: 12px;
}

.shop-edit-dialog__field--full {
  grid-column: 1 / -1;
}

.shop-edit-dialog__cookie,
.shop-edit-dialog__knowledge-list {
  padding: 10px 12px;
  border-radius: 14px;
  background: #f6f8fb;
}

.shop-edit-dialog__cookie {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  color: #44586f;
}

.shop-edit-dialog__knowledge-list {
  display: grid;
  gap: 10px;
  max-height: 220px;
  overflow: auto;
}

.shop-edit-dialog__rules {
  display: grid;
  gap: 12px;
}

.shop-edit-dialog__rule-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) auto;
  gap: 12px;
}

.shop-edit-dialog__rule-type {
  width: 100%;
}

@media (max-width: 720px) {
  .shop-edit-dialog__grid {
    grid-template-columns: 1fr;
  }

  .shop-edit-dialog__rule-row {
    grid-template-columns: 1fr;
  }
}
</style>
