import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { SystemSettings, WebhookType } from '@/types/settings';

export async function fetchSettings(): Promise<SystemSettings> {
  return unwrapResponse(request.get<ApiResponse<SystemSettings>>('/settings'));
}

export async function testLlmConnection(params: {
  apiBaseUrl: string;
  apiKey: string;
  model: string;
}): Promise<{ ok: boolean; message: string }> {
  return unwrapResponse(
    request.post<ApiResponse<{ ok: boolean; message: string }>>('/settings/test-llm', params),
  );
}

export async function saveSettings(settings: SystemSettings): Promise<SystemSettings> {
  return unwrapResponse(request.put<ApiResponse<SystemSettings>>('/settings', settings));
}

export async function testWebhook(params: {
  url: string;
  webhookType: WebhookType;
}): Promise<{ ok: boolean; message: string }> {
  return unwrapResponse(
    request.post<ApiResponse<{ ok: boolean; message: string }>>('/settings/test-webhook', params),
  );
}
