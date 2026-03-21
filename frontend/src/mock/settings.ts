import type { MockMethod } from 'vite-plugin-mock';

import type { SystemSettings } from '@/types/settings';

interface SettingsRequest {
  body?: SystemSettings;
}

let settingsState: SystemSettings = {
  apiBaseUrl: 'https://api.deepseek.com/v1/chat/completions',
  apiKey: 'sk-demo-global-key',
  defaultModel: 'deepseek-chat',
  temperature: 0.7,
  maxTokens: 500,
  defaultFallbackMsg: '亲，已为您转接人工客服，请稍等~',
  defaultKeywords: ['退款', '人工', '投诉'],
  logLevel: 'INFO',
  historyRetentionDays: 30,
  notifyWebhookUrl: 'https://example.com/webhook/demo',
  notifyWebhookType: 'feishu',
  maxShops: 10,
};

const settingsMocks: MockMethod[] = [
  {
    url: '/api/settings',
    method: 'get',
    response: () => ({
      code: 0,
      msg: 'success',
      data: settingsState,
    }),
  },
  {
    url: '/api/settings',
    method: 'put',
    response: ({ body }: SettingsRequest) => {
      settingsState = {
        ...settingsState,
        ...body,
      };

      return {
        code: 0,
        msg: 'success',
        data: settingsState,
      };
    },
  },
  {
    url: '/api/settings/test-llm',
    method: 'post',
    response: async () => {
      await new Promise((resolve) => {
        setTimeout(resolve, 1000);
      });

      return {
        code: 0,
        msg: 'success',
        data: {
          ok: true,
          message: 'LLM 连接测试成功，模型响应正常',
        },
      };
    },
  },
  {
    url: '/api/settings/test-webhook',
    method: 'post',
    response: async () => {
      await new Promise((resolve) => {
        setTimeout(resolve, 500);
      });

      return {
        code: 0,
        msg: 'success',
        data: {
          ok: true,
          message: '发送成功',
        },
      };
    },
  },
];

export default settingsMocks;
