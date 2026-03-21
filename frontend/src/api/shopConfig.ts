import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { ShopConfig, ShopConfigSavePayload } from '@/types/shopConfig';

export async function fetchShopConfig(shopId: string): Promise<ShopConfig> {
  return unwrapResponse(request.get<ApiResponse<ShopConfig>>(`/shops/${shopId}/config`));
}

export async function saveShopConfig(
  shopId: string,
  config: ShopConfigSavePayload,
): Promise<ShopConfig> {
  return unwrapResponse(request.put<ApiResponse<ShopConfig>>(`/shops/${shopId}/config`, config));
}
