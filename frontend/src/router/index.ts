import {
  ChatDotRound,
  DataBoard,
  Document,
  Setting,
  Shop,
} from '@element-plus/icons-vue';
import type { Component } from 'vue';
import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
} from 'vue-router';

export const routeIconMap = {
  DataBoard,
  Shop,
  ChatDotRound,
  Document,
  Setting,
} as const;

declare module 'vue-router' {
  interface RouteMeta {
    title?: string;
    icon?: keyof typeof routeIconMap;
    hidden?: boolean;
  }
}

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '总览', icon: 'DataBoard' },
  },
  {
    path: '/shops',
    component: () => import('@/views/ShopManage.vue'),
    meta: { title: '店铺管理', icon: 'Shop' },
  },
  {
    path: '/shops/edit/:id?',
    component: () => import('@/views/ShopEdit.vue'),
    meta: { title: '编辑店铺', hidden: true },
  },
  {
    path: '/chat',
    component: () => import('@/views/ChatMonitor.vue'),
    meta: { title: '对话监控', icon: 'ChatDotRound' },
  },
  {
    path: '/knowledge',
    component: () => import('@/views/KnowledgeBase.vue'),
    meta: { title: '知识库', icon: 'Document' },
  },
  {
    path: '/settings',
    component: () => import('@/views/Settings.vue'),
    meta: { title: '系统设置', icon: 'Setting' },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.afterEach((to) => {
  const title = to.meta.title ?? '多平台电商智能客服';
  document.title = `${title} | 多平台电商智能客服`;
});

export function resolveRouteIcon(icon?: keyof typeof routeIconMap): Component | null {
  return icon ? routeIconMap[icon] : null;
}

export default router;
