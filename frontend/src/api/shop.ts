import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { Shop } from '@/types/shop';

export interface CreateShopBody {
  name: string;
  platform: 'pdd';
  username: string;
  password: string;
}

export async function fetchShopList(): Promise<Shop[]> {
  return unwrapResponse(request.get<ApiResponse<Shop[]>>('/shops'));
}

export async function createShop(body: CreateShopBody): Promise<Shop> {
  return unwrapResponse(request.post<ApiResponse<Shop>>('/shops', body));
}

export async function toggleShopAi(shopId: string, enabled: boolean): Promise<Shop> {
  return unwrapResponse(request.patch<ApiResponse<Shop>>(`/shops/${shopId}/ai`, { enabled }));
}

export async function toggleShopStatus(shopId: string): Promise<Shop> {
  return unwrapResponse(request.post<ApiResponse<Shop>>(`/shops/${shopId}/toggle`));
}

export async function deleteShop(shopId: string): Promise<null> {
  return unwrapResponse(request.delete<ApiResponse<null>>(`/shops/${shopId}`));
}

export async function openShopBrowser(shopId: string): Promise<null> {
  return unwrapResponse(request.post<ApiResponse<null>>(`/shops/${shopId}/open-browser`));
}

export async function scanDesktopWindows(): Promise<Shop[]> {
  return unwrapResponse(request.post<ApiResponse<Shop[]>>('/shops/scan'));
}
