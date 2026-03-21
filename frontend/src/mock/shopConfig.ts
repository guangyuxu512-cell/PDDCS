import type { MockMethod } from 'vite-plugin-mock';

import type { ShopConfig } from '@/types/shopConfig';

interface ShopConfigMockRequest {
  body?: Partial<ShopConfig> & { password?: string };
  url?: string;
}

let shopConfigs: Record<string, ShopConfig> = {
  'shop-pdd-001': {
    shopId: 'shop-pdd-001',
    name: '拼多多旗舰店',
    username: 'pdd_admin_001',
    platform: 'pdd',
    cookieValid: true,
    aiEnabled: true,
    hasPassword: true,
    cookieFingerprint: 'a1b2c3d4',
    llmMode: 'global',
    replyStyleNote: '语气亲切，尽量简洁。',
    knowledgePaths: ['shops/拼多多旗舰店/活动规则.md'],
    useGlobalKnowledge: true,
    humanAgentName: '小陈客服',
    escalationRules: [
      { id: 'rule-pdd-001', type: 'keyword', value: '退款' },
      { id: 'rule-pdd-002', type: 'repeat_ask', value: '3' },
    ],
    escalationFallbackMsg: '亲，已为您转接人工客服，请稍等',
    autoRestart: false,
    forceOnline: true,
  },
  'shop-pdd-002': {
    shopId: 'shop-pdd-002',
    name: '拼多多百货店',
    username: 'pdd_store_ops',
    platform: 'pdd',
    cookieValid: true,
    aiEnabled: false,
    hasPassword: true,
    cookieFingerprint: 'b2c3d4e5',
    llmMode: 'custom',
    customApiKey: 'sk-demo-pdd-002',
    customModel: 'deepseek-chat',
    replyStyleNote: '优先说明活动和发货时效。',
    knowledgePaths: ['global/发货说明.md', 'global/售后政策.md'],
    useGlobalKnowledge: true,
    humanAgentName: '百货人工客服',
    escalationRules: [{ id: 'rule-pdd-003', type: 'order_amount', value: '500' }],
    escalationFallbackMsg: '亲，当前问题已转接人工处理，请稍等。',
    autoRestart: true,
    forceOnline: false,
  },
  'shop-dy-001': {
    shopId: 'shop-dy-001',
    name: '抖店服饰专营',
    username: 'douyin_fashion',
    platform: 'douyin',
    cookieValid: true,
    aiEnabled: true,
    hasPassword: true,
    cookieFingerprint: 'c3d4e5f6',
    llmMode: 'global',
    replyStyleNote: '多引导用户查看尺码表。',
    knowledgePaths: ['shops/抖店服饰专营/尺码建议.md'],
    useGlobalKnowledge: false,
    humanAgentName: '抖店售后组',
    escalationRules: [{ id: 'rule-dy-001', type: 'regex', value: '退.*赔偿' }],
    escalationFallbackMsg: '您好，已为您转接人工客服，请稍后。',
    autoRestart: false,
    forceOnline: false,
  },
};

const shopConfigMocks: MockMethod[] = [
  {
    url: '/api/shops/:id/config',
    method: 'get',
    response: ({ url }: ShopConfigMockRequest) => {
      const shopId = url?.split('/').slice(-2)[0] ?? '';
      const config = shopConfigs[shopId];

      return {
        code: config ? 0 : 404,
        msg: config ? 'success' : 'shop config not found',
        data: config,
      };
    },
  },
  {
    url: '/api/shops/:id/config',
    method: 'put',
    response: ({ body, url }: ShopConfigMockRequest) => {
      const shopId = url?.split('/').slice(-2)[0] ?? '';
      if (!body) {
        return {
          code: 400,
          msg: 'invalid payload',
          data: null,
        };
      }

      const currentConfig = shopConfigs[shopId];
      if (!currentConfig) {
        return {
          code: 404,
          msg: 'shop config not found',
          data: null,
        };
      }

      shopConfigs = {
        ...shopConfigs,
        [shopId]: {
          ...currentConfig,
          ...body,
          shopId,
          hasPassword: body.password ? true : currentConfig.hasPassword,
        },
      };

      return {
        code: 0,
        msg: 'success',
        data: shopConfigs[shopId],
      };
    },
  },
];

export default shopConfigMocks;
