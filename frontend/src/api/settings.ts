import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { SystemSettings } from '@/types/settings';

export async function fetchSettings(): Promise<SystemSettings> {
  return unwrapResponse(request.get<ApiResponse<SystemSettings>>('/settings'));
}

export async function saveSettings(settings: SystemSettings): Promise<SystemSettings> {
  return unwrapResponse(request.put<ApiResponse<SystemSettings>>('/settings', settings));
}
