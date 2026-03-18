import type { MockMethod } from 'vite-plugin-mock';

const dashboardMocks: MockMethod[] = [
  {
    url: '/api/dashboard/summary',
    method: 'get',
    response: () => ({
      code: 0,
      msg: 'success',
      data: {
        activeShopCount: 8,
        pendingEscalations: 3,
        todayMessages: 286,
        automationRate: 0.91,
      },
    }),
  },
];

export default dashboardMocks;
