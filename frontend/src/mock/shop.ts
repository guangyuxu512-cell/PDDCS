import type { MockMethod } from 'vite-plugin-mock';

import type { Shop } from '@/types/shop';

interface ShopMockRequest {
  body?: {
    enabled?: boolean;
  };
  url?: string;
}

let shops: Shop[] = [
  {
    id: 'shop-pdd-001',
    name: '拼多多旗舰店',
    platform: 'pdd',
    isOnline: true,
    aiEnabled: true,
    todayServedCount: 86,
    lastActiveAt: '2026-03-19T10:28:00+08:00',
    cookieValid: true,
    hasPassword: true,
    cookieFingerprint: 'a1b2c3d4',
  },
  {
    id: 'shop-pdd-002',
    name: '拼多多百货店',
    platform: 'pdd',
    isOnline: false,
    aiEnabled: false,
    todayServedCount: 31,
    lastActiveAt: '2026-03-19T08:41:00+08:00',
    cookieValid: true,
    hasPassword: true,
    cookieFingerprint: 'b2c3d4e5',
  },
  {
    id: 'shop-dy-001',
    name: '抖店服饰专营',
    platform: 'douyin',
    isOnline: true,
    aiEnabled: true,
    todayServedCount: 64,
    lastActiveAt: '2026-03-19T10:11:00+08:00',
    cookieValid: true,
    hasPassword: true,
    cookieFingerprint: 'c3d4e5f6',
  },
  {
    id: 'shop-dy-002',
    name: '抖店美妆优选',
    platform: 'douyin',
    isOnline: true,
    aiEnabled: false,
    todayServedCount: 52,
    lastActiveAt: '2026-03-19T09:56:00+08:00',
    cookieValid: false,
    hasPassword: true,
    cookieFingerprint: '',
  },
  {
    id: 'shop-qn-001',
    name: '千牛家居馆',
    platform: 'qianniu',
    isOnline: false,
    aiEnabled: true,
    todayServedCount: 23,
    lastActiveAt: '2026-03-19T07:32:00+08:00',
    cookieValid: true,
    hasPassword: true,
    cookieFingerprint: 'd4e5f6a7',
  },
  {
    id: 'shop-qn-002',
    name: '千牛食品店',
    platform: 'qianniu',
    isOnline: true,
    aiEnabled: true,
    todayServedCount: 47,
    lastActiveAt: '2026-03-19T10:05:00+08:00',
    cookieValid: true,
    hasPassword: true,
    cookieFingerprint: 'e5f6a7b8',
  },
  {
    id: 'shop-qn-003',
    name: '千牛母婴旗舰',
    platform: 'qianniu',
    isOnline: false,
    aiEnabled: false,
    todayServedCount: 15,
    lastActiveAt: '2026-03-19T06:58:00+08:00',
    cookieValid: false,
    hasPassword: false,
    cookieFingerprint: '',
  },
];

function updateShop(shopId: string, updater: (shop: Shop) => Shop): Shop | null {
  const index = shops.findIndex((shop) => shop.id === shopId);
  if (index < 0) {
    return null;
  }

  const nextShop = updater(shops[index]);
  shops = shops.map((shop, currentIndex) => (currentIndex === index ? nextShop : shop));
  return nextShop;
}

const shopMocks: MockMethod[] = [
  {
    url: '/api/shops',
    method: 'get',
    response: () => ({
      code: 0,
      msg: 'success',
      data: shops,
    }),
  },
  {
    url: '/api/shops/:id/ai',
    method: 'patch',
    response: ({ body, url }: ShopMockRequest) => {
      const shopId = url?.split('/').slice(-2)[0] ?? '';
      const enabled = typeof body?.enabled === 'boolean' ? body.enabled : Boolean(body?.enabled);
      const updatedShop = updateShop(shopId, (shop) => ({
        ...shop,
        aiEnabled: enabled,
      }));

      return {
        code: updatedShop ? 0 : 404,
        msg: updatedShop ? 'success' : 'shop not found',
        data: updatedShop,
      };
    },
  },
  {
    url: '/api/shops/:id/toggle',
    method: 'post',
    response: ({ url }: ShopMockRequest) => {
      const shopId = url?.split('/').slice(-2)[0] ?? '';
      const updatedShop = updateShop(shopId, (shop) => ({
        ...shop,
        isOnline: !shop.isOnline,
        lastActiveAt: new Date().toISOString(),
      }));

      return {
        code: updatedShop ? 0 : 404,
        msg: updatedShop ? 'success' : 'shop not found',
        data: updatedShop,
      };
    },
  },
  {
    url: '/api/shops/:id/open-browser',
    method: 'post',
    response: () => ({
      code: 0,
      msg: 'success',
      data: null,
    }),
  },
  {
    url: '/api/shops/:id/start',
    method: 'post',
    response: ({ url }: ShopMockRequest) => {
      const shopId = url?.split('/').slice(-2)[0] ?? '';
      const updatedShop = updateShop(shopId, (shop) => ({
        ...shop,
        isOnline: true,
        lastActiveAt: new Date().toISOString(),
      }));

      return {
        code: updatedShop ? 0 : 404,
        msg: updatedShop ? 'success' : 'shop not found',
        data: null,
      };
    },
  },
  {
    url: '/api/shops/:id/stop',
    method: 'post',
    response: ({ url }: ShopMockRequest) => {
      const shopId = url?.split('/').slice(-2)[0] ?? '';
      const updatedShop = updateShop(shopId, (shop) => ({
        ...shop,
        isOnline: false,
        lastActiveAt: new Date().toISOString(),
      }));

      return {
        code: updatedShop ? 0 : 404,
        msg: updatedShop ? 'success' : 'shop not found',
        data: null,
      };
    },
  },
];

export default shopMocks;
