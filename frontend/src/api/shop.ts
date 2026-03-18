import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { Shop } from '@/types/shop';

export async function fetchShopList(): Promise<Shop[]> {
  return unwrapResponse(request.get<ApiResponse<Shop[]>>('/shops'));
}

export async function toggleShopAi(shopId: string, enabled: boolean): Promise<Shop> {
  return unwrapResponse(request.patch<ApiResponse<Shop>>(`/shops/${shopId}/ai`, { enabled }));
}

export async function toggleShopStatus(shopId: string): Promise<Shop> {
  return unwrapResponse(request.post<ApiResponse<Shop>>(`/shops/${shopId}/toggle`));
}
