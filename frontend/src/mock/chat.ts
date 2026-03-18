import type { MockMethod } from 'vite-plugin-mock';

import type { ChatSession } from '@/types/chat';

interface ChatRequest {
  url?: string;
}

let sessions: ChatSession[] = [
  {
    id: 'session-001',
    buyerId: 'buyer-001',
    buyerName: '柚子同学',
    shopId: 'shop-pdd-001',
    shopName: '拼多多旗舰店',
    platform: 'pdd',
    status: 'ai_processing',
    lastMessagePreview: '好的，预计今天下午可以发出吗？',
    updatedAt: '2026-03-19T10:18:00+08:00',
    messages: [
      { id: 'msg-001', sender: 'buyer', content: '这款今天能发货吗？', createdAt: '2026-03-19T10:10:00+08:00' },
      { id: 'msg-002', sender: 'ai', content: '亲，当前订单会在 24 小时内安排发货。', createdAt: '2026-03-19T10:11:00+08:00' },
      { id: 'msg-003', sender: 'buyer', content: '我比较着急，今天能发吗？', createdAt: '2026-03-19T10:12:00+08:00' },
      { id: 'msg-004', sender: 'ai', content: '我这边帮您优先催仓，稍后给您确认结果。', createdAt: '2026-03-19T10:14:00+08:00' },
      { id: 'msg-005', sender: 'buyer', content: '好的，预计今天下午可以发出吗？', createdAt: '2026-03-19T10:18:00+08:00' },
    ],
  },
  {
    id: 'session-002',
    buyerId: 'buyer-002',
    buyerName: 'Mia',
    shopId: 'shop-dy-001',
    shopName: '抖店服饰专营',
    platform: 'douyin',
    status: 'escalated',
    lastMessagePreview: '已经转人工啦，麻烦尽快帮我处理一下尺码问题。',
    updatedAt: '2026-03-19T10:06:00+08:00',
    messages: [
      { id: 'msg-006', sender: 'buyer', content: '这件外套偏大还是偏小？', createdAt: '2026-03-19T09:54:00+08:00' },
      { id: 'msg-007', sender: 'ai', content: '建议参考页面尺码表，如果您告诉我身高体重，我也可以帮您推荐。', createdAt: '2026-03-19T09:55:00+08:00' },
      { id: 'msg-008', sender: 'buyer', content: '我 165/52，想穿宽松一点。', createdAt: '2026-03-19T09:58:00+08:00' },
      { id: 'msg-009', sender: 'human', content: '您好，这边建议 M 码会更宽松一些，我来帮您详细确认。', createdAt: '2026-03-19T10:06:00+08:00' },
      { id: 'msg-010', sender: 'buyer', content: '已经转人工啦，麻烦尽快帮我处理一下尺码问题。', createdAt: '2026-03-19T10:06:00+08:00' },
    ],
  },
  {
    id: 'session-003',
    buyerId: 'buyer-003',
    buyerName: '家居采购王',
    shopId: 'shop-qn-001',
    shopName: '千牛家居馆',
    platform: 'qianniu',
    status: 'closed',
    lastMessagePreview: '明白了，那我直接下单。',
    updatedAt: '2026-03-19T09:46:00+08:00',
    messages: [
      { id: 'msg-011', sender: 'buyer', content: '这个书柜需要自己安装吗？', createdAt: '2026-03-19T09:35:00+08:00' },
      { id: 'msg-012', sender: 'ai', content: '亲，需要简单安装，页面详情里有安装视频。', createdAt: '2026-03-19T09:36:00+08:00' },
      { id: 'msg-013', sender: 'buyer', content: '那配件会一起发吗？', createdAt: '2026-03-19T09:40:00+08:00' },
      { id: 'msg-014', sender: 'ai', content: '会的，螺丝和工具会随包裹一起寄出。', createdAt: '2026-03-19T09:41:00+08:00' },
      { id: 'msg-015', sender: 'buyer', content: '明白了，那我直接下单。', createdAt: '2026-03-19T09:46:00+08:00' },
    ],
  },
  {
    id: 'session-004',
    buyerId: 'buyer-004',
    buyerName: '小丸子妈妈',
    shopId: 'shop-qn-003',
    shopName: '千牛母婴旗舰',
    platform: 'qianniu',
    status: 'ai_processing',
    lastMessagePreview: '这个配方奶粉适合一岁宝宝吗？',
    updatedAt: '2026-03-19T10:22:00+08:00',
    messages: [
      { id: 'msg-016', sender: 'buyer', content: '这个配方奶粉适合一岁宝宝吗？', createdAt: '2026-03-19T10:17:00+08:00' },
      { id: 'msg-017', sender: 'ai', content: '亲，这款适用于 12 个月以上宝宝，建议结合页面说明确认月龄段。', createdAt: '2026-03-19T10:18:00+08:00' },
      { id: 'msg-018', sender: 'buyer', content: '那肠胃敏感能喝吗？', createdAt: '2026-03-19T10:20:00+08:00' },
      { id: 'msg-019', sender: 'ai', content: '如果宝宝体质比较敏感，建议先咨询医生或专业营养师。', createdAt: '2026-03-19T10:21:00+08:00' },
      { id: 'msg-020', sender: 'buyer', content: '这个配方奶粉适合一岁宝宝吗？', createdAt: '2026-03-19T10:22:00+08:00' },
    ],
  },
];

const chatMocks: MockMethod[] = [
  {
    url: '/api/chat/sessions',
    method: 'get',
    response: () => ({
      code: 0,
      msg: 'success',
      data: sessions,
    }),
  },
  {
    url: '/api/chat/sessions/:id/takeover',
    method: 'post',
    response: ({ url }: ChatRequest) => {
      const sessionId = url?.split('/').slice(-2)[0] ?? '';
      const index = sessions.findIndex((session) => session.id === sessionId);
      if (index < 0) {
        return { code: 404, msg: 'session not found', data: null };
      }

      const updatedSession: ChatSession = {
        ...sessions[index],
        status: 'escalated',
        updatedAt: new Date().toISOString(),
        lastMessagePreview: '人工客服已接管当前会话。',
        messages: [
          ...sessions[index].messages,
          {
            id: `msg-takeover-${Date.now()}`,
            sender: 'human',
            content: '您好，我已接管当前会话，接下来由我为您处理。',
            createdAt: new Date().toISOString(),
          },
        ],
      };
      sessions = sessions.map((session, currentIndex) =>
        currentIndex === index ? updatedSession : session,
      );

      return {
        code: 0,
        msg: 'success',
        data: updatedSession,
      };
    },
  },
];

export default chatMocks;
