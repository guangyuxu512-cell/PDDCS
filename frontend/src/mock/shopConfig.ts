import type { MockMethod } from 'vite-plugin-mock';

import type { ShopConfig } from '@/types/shopConfig';

interface ShopConfigMockRequest {
  body?: ShopConfig;
  url?: string;
}

let shopConfigs: Record<string, ShopConfig> = {
  'shop-pdd-001': {
    shopId: 'shop-pdd-001',
    name: '拼多多旗舰店',
    username: 'pdd_admin_001',
    password: 'Pdd@123456',
    platform: 'pdd',
    cookieValid: true,
    cookieLastRefresh: '2026-03-19T09:42:00+08:00',
    aiEnabled: true,
    llmMode: 'global',
    replyStyleNote: '语气亲切，尽量简洁。',
    knowledgePaths: ['shops/拼多多旗舰店/活动规则.md'],
    useGlobalKnowledge: true,
    humanAgentName: '小陈客服',
    escalationRules: [
      { id: 'rule-pdd-001', type: 'keyword', value: '退款' },
      { id: 'rule-pdd-002', type: 'repeat_ask', value: '3' },
    ],
    escalationFallbackMsg: '亲，已为您转接人工客服，请稍等~',
    autoRestart: false,
    forceOnline: true,
  },
  'shop-pdd-002': {
    shopId: 'shop-pdd-002',
    name: '拼多多百货店',
    username: 'pdd_store_ops',
    password: 'Pdd#Ops2026',
    platform: 'pdd',
    cookieValid: true,
    cookieLastRefresh: '2026-03-18T22:08:00+08:00',
    aiEnabled: false,
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
    password: 'DyFashion!88',
    platform: 'douyin',
    cookieValid: true,
    cookieLastRefresh: '2026-03-19T10:01:00+08:00',
    aiEnabled: true,
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
  'shop-dy-002': {
    shopId: 'shop-dy-002',
    name: '抖店美妆优选',
    username: 'douyin_beauty',
    password: 'Beauty@2026',
    platform: 'douyin',
    cookieValid: false,
    cookieLastRefresh: '2026-03-18T18:18:00+08:00',
    aiEnabled: false,
    llmMode: 'custom',
    customApiKey: 'sk-demo-dy-002',
    customModel: 'gpt-4o-mini',
    replyStyleNote: '用词精致，强调成分和肤质匹配。',
    knowledgePaths: ['global/售后政策.md'],
    useGlobalKnowledge: true,
    humanAgentName: '美妆顾问',
    escalationRules: [{ id: 'rule-dy-002', type: 'keyword', value: '过敏' }],
    escalationFallbackMsg: '您好，当前问题需要人工协助，已经为您转接。',
    autoRestart: true,
    forceOnline: true,
  },
  'shop-qn-001': {
    shopId: 'shop-qn-001',
    name: '千牛家居馆',
    username: 'qianniu_home',
    password: 'Home&Life99',
    platform: 'qianniu',
    cookieValid: true,
    cookieLastRefresh: '2026-03-19T07:16:00+08:00',
    aiEnabled: true,
    llmMode: 'global',
    replyStyleNote: '优先说明安装方式和材质。',
    knowledgePaths: ['shops/千牛家居馆/安装说明.md'],
    useGlobalKnowledge: true,
    humanAgentName: '家居人工一组',
    escalationRules: [{ id: 'rule-qn-001', type: 'repeat_ask', value: '2' }],
    escalationFallbackMsg: '亲，已为您联系人工客服，请稍等片刻。',
    autoRestart: false,
    forceOnline: false,
  },
  'shop-qn-002': {
    shopId: 'shop-qn-002',
    name: '千牛食品店',
    username: 'qianniu_food',
    password: 'FoodSafe#66',
    platform: 'qianniu',
    cookieValid: true,
    cookieLastRefresh: '2026-03-19T09:47:00+08:00',
    aiEnabled: true,
    llmMode: 'global',
    replyStyleNote: '多强调保质期和发货时效。',
    knowledgePaths: ['global/发货说明.md'],
    useGlobalKnowledge: true,
    humanAgentName: '食品人工客服',
    escalationRules: [{ id: 'rule-qn-002', type: 'keyword', value: '临期' }],
    escalationFallbackMsg: '亲，已为您转接人工客服协助处理。',
    autoRestart: true,
    forceOnline: true,
  },
  'shop-qn-003': {
    shopId: 'shop-qn-003',
    name: '千牛母婴旗舰',
    username: 'qianniu_baby',
    password: 'BabyCare@520',
    platform: 'qianniu',
    cookieValid: false,
    cookieLastRefresh: '2026-03-18T17:28:00+08:00',
    aiEnabled: false,
    llmMode: 'custom',
    customApiKey: 'sk-demo-qn-003',
    customModel: 'qwen-max',
    replyStyleNote: '避免绝对化承诺，重视安全表述。',
    knowledgePaths: ['global/售后政策.md'],
    useGlobalKnowledge: true,
    humanAgentName: '母婴人工客服',
    escalationRules: [{ id: 'rule-qn-003', type: 'keyword', value: '宝宝不适' }],
    escalationFallbackMsg: '亲，已为您转接人工客服，请稍等回复。',
    autoRestart: false,
    forceOnline: true,
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

      shopConfigs = {
        ...shopConfigs,
        [shopId]: {
          ...body,
          shopId,
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
