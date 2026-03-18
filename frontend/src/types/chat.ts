import type { Platform } from '@/types/shop';

export type ChatSessionStatus = 'ai_processing' | 'escalated' | 'closed';
export type ChatMessageSender = 'buyer' | 'ai' | 'human';

export interface ChatMessage {
  id: string;
  sender: ChatMessageSender;
  content: string;
  createdAt: string;
}

export interface ChatSession {
  id: string;
  buyerId: string;
  buyerName: string;
  shopId: string;
  shopName: string;
  platform: Platform;
  status: ChatSessionStatus;
  lastMessagePreview: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export const chatStatusLabel: Record<ChatSessionStatus, string> = {
  ai_processing: 'AI处理中',
  escalated: '已转人工',
  closed: '已结束',
};
