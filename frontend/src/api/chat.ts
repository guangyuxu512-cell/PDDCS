import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { ChatSession } from '@/types/chat';

export async function fetchChatSessions(): Promise<ChatSession[]> {
  return unwrapResponse(request.get<ApiResponse<ChatSession[]>>('/chat/sessions'));
}

export async function takeoverChatSession(sessionId: string): Promise<ChatSession> {
  return unwrapResponse(request.post<ApiResponse<ChatSession>>(`/chat/sessions/${sessionId}/takeover`));
}
