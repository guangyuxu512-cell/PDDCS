import type { MockMethod } from 'vite-plugin-mock';

const dashboardMocks: MockMethod[] = [
  {
    url: '/api/dashboard/summary',
    method: 'get',
    response: () => ({
      code: 0,
      msg: 'success',
      data: {
        todayServedCount: 286,
        aiReplyRate: 0.912,
        escalationCount: 5,
        avgFirstResponseMs: 2300,
        unrepliedCount: 2,
        yesterdayServedCount: 255,
      },
    }),
  },
];

export default dashboardMocks;
