export type Platform = 'pdd' | 'douyin' | 'qianniu';

export interface Shop {
  id: string;
  name: string;
  platform: Platform;
  isOnline: boolean;
  aiEnabled: boolean;
  todayServedCount: number;
  lastActiveAt: string;
  cookieValid: boolean;
}

export const platformLabel: Record<Platform, string> = {
  pdd: '拼多多',
  douyin: '抖店',
  qianniu: '千牛',
};
