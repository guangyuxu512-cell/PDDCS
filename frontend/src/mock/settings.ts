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
  alertWebhookUrl: 'https://example.com/webhook/demo',
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
];

export default settingsMocks;
