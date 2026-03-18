import type { Platform } from '@/types/shop';

export type EscalationRuleType = 'keyword' | 'repeat_ask' | 'order_amount' | 'regex';

export interface EscalationRule {
  id: string;
  type: EscalationRuleType;
  value: string;
}

export interface ShopConfig {
  shopId: string;
  name: string;
  platform: Platform;
  cookieValid: boolean;
  cookieLastRefresh: string;
  aiEnabled: boolean;
  llmMode: 'global' | 'custom';
  customApiKey?: string;
  customModel?: string;
  replyStyleNote?: string;
  humanAgentName: string;
  escalationRules: EscalationRule[];
  escalationFallbackMsg: string;
}
