export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
export type WebhookType = 'feishu' | 'dingtalk' | 'wecom' | 'generic';

export interface SystemSettings {
  apiBaseUrl: string;
  apiKey: string;
  defaultModel: string;
  temperature: number;
  maxTokens: number;
  defaultFallbackMsg: string;
  defaultKeywords: string[];
  logLevel: LogLevel;
  historyRetentionDays: number;
  notifyWebhookUrl: string;
  notifyWebhookType: WebhookType;
  maxShops: number;
}
