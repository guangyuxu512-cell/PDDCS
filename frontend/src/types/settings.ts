export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';

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
  alertWebhookUrl: string;
  maxShops: number;
}
