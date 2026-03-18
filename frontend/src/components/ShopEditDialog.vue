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
            <div class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>Cookie 状态</span>
              <div class="shop-edit-dialog__cookie">
                <el-tag :type="formState.cookieValid ? 'success' : 'danger'" round>
                  {{ formState.cookieValid ? '有效' : '已过期' }}
                </el-tag>
                <span>上次刷新时间：{{ cookieLastRefreshText }}</span>
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
              <span>LLM 模型</span>
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
            <label class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>回复风格备注</span>
              <el-input
                v-model="formState.replyStyleNote"
                :rows="3"
                placeholder="例如：语气亲切，多用 emoji"
                type="textarea"
              />
            </label>
          </div>
        </el-collapse-item>

        <el-collapse-item name="escalation" title="转人工规则">
          <div class="shop-edit-dialog__grid">
            <label class="shop-edit-dialog__field shop-edit-dialog__field--full">
              <span>人工客服账号名</span>
              <el-input v-model="formState.humanAgentName" placeholder="请输入 RPA 转接的目标客服名" />
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
                placeholder="例如：亲，已为您转接人工客服，请稍等~"
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

import { fetchShopConfig, saveShopConfig } from '@/api/shopConfig';
import { platformLabel, type Platform } from '@/types/shop';
import {
  type EscalationRule,
  type EscalationRuleType,
  type ShopConfig,
} from '@/types/shopConfig';

const props = defineProps<{
  modelValue: boolean;
  shopId: string | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [config: ShopConfig];
}>();

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

const activePanels = ref<Array<'basic' | 'ai' | 'escalation'>>(['basic', 'ai', 'escalation']);
const loading = ref(false);
const saving = ref(false);
const formState = ref<ShopConfig>(createEmptyConfig());

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
});

const cookieLastRefreshText = computed(() =>
  formState.value.cookieLastRefresh
    ? new Date(formState.value.cookieLastRefresh).toLocaleString('zh-CN')
    : '--',
);

watch(
  () => [props.modelValue, props.shopId] as const,
  async ([visible, shopId]) => {
    if (!visible || !shopId) {
      return;
    }

    loading.value = true;
    try {
      formState.value = normalizeConfig(await fetchShopConfig(shopId));
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '店铺配置加载失败');
    } finally {
      loading.value = false;
    }
  },
);

function createEmptyConfig(): ShopConfig {
  return {
    shopId: '',
    name: '',
    platform: 'pdd',
    cookieValid: false,
    cookieLastRefresh: '',
    aiEnabled: false,
    llmMode: 'global',
    customApiKey: '',
    customModel: '',
    replyStyleNote: '',
    humanAgentName: '',
    escalationRules: [],
    escalationFallbackMsg: '',
  };
}

function normalizeConfig(config: ShopConfig): ShopConfig {
  return {
    ...config,
    customApiKey: config.customApiKey ?? '',
    customModel: config.customModel ?? '',
    replyStyleNote: config.replyStyleNote ?? '',
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

async function handleSave(): Promise<void> {
  if (!props.shopId) {
    ElMessage.error('缺少店铺 ID，无法保存');
    return;
  }

  if (!formState.value.name.trim()) {
    ElMessage.error('店铺名称不能为空');
    return;
  }

  if (!formState.value.humanAgentName.trim()) {
    ElMessage.error('人工客服账号名不能为空');
    return;
  }

  saving.value = true;
  try {
    const savedConfig = await saveShopConfig(props.shopId, normalizeSavePayload(formState.value));
    const normalized = normalizeConfig(savedConfig);
    formState.value = normalized;
    emit('saved', normalized);
    dialogVisible.value = false;
    ElMessage.success('店铺配置已保存');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '店铺配置保存失败');
  } finally {
    saving.value = false;
  }
}

function normalizeSavePayload(config: ShopConfig): ShopConfig {
  return {
    ...config,
    shopId: props.shopId ?? config.shopId,
    customApiKey: config.llmMode === 'custom' ? config.customApiKey?.trim() ?? '' : undefined,
    customModel: config.llmMode === 'custom' ? config.customModel?.trim() ?? '' : undefined,
    replyStyleNote: config.replyStyleNote?.trim() ?? '',
    humanAgentName: config.humanAgentName.trim(),
    escalationRules: config.escalationRules.map((rule) => ({
      ...rule,
      value: rule.value.trim(),
    })),
    escalationFallbackMsg: config.escalationFallbackMsg.trim(),
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

.shop-edit-dialog__field--full {
  grid-column: 1 / -1;
}

.shop-edit-dialog__cookie {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  padding: 10px 12px;
  border-radius: 14px;
  background: #f6f8fb;
  color: #44586f;
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
