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
  username: string;
  platform: Platform;
  cookieValid: boolean;
  aiEnabled: boolean;
  hasPassword: boolean;
  cookieFingerprint: string;
  llmMode: 'global' | 'custom';
  customApiKey?: string;
  customModel?: string;
  replyStyleNote?: string;
  knowledgePaths: string[];
  useGlobalKnowledge: boolean;
  humanAgentName: string;
  escalationRules: EscalationRule[];
  escalationFallbackMsg: string;
  autoRestart: boolean;
  forceOnline: boolean;
}

export interface ShopConfigSavePayload
  extends Omit<ShopConfig, 'hasPassword' | 'cookieFingerprint'> {
  password?: string;
}
