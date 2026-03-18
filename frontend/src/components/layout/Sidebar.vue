<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <h1>多平台智能客服</h1>
      <span>RPA 自动化客服系统</span>
    </div>

    <el-menu
      :default-active="activePath"
      class="sidebar__menu"
      background-color="transparent"
      text-color="#d7e0ef"
      active-text-color="#ffffff"
      @select="handleSelect"
    >
      <el-menu-item
        v-for="routeItem in visibleRoutes"
        :key="routeItem.path"
        :index="routeItem.path"
        class="sidebar__menu-item"
      >
        <el-icon v-if="routeItem.icon">
          <component :is="resolveRouteIcon(routeItem.icon)" />
        </el-icon>
        <span>{{ routeItem.title }}</span>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { resolveRouteIcon, routes } from '@/router';

const router = useRouter();
const route = useRoute();

const visibleRoutes = computed(() =>
  routes
    .filter(
      (routeItem) =>
        routeItem.path !== '/' &&
        !routeItem.meta?.hidden &&
        typeof routeItem.component === 'function' &&
        !!routeItem.meta?.title,
    )
    .map((routeItem) => ({
      path: routeItem.path,
      title: routeItem.meta?.title ?? '',
      icon: routeItem.meta?.icon,
    })),
);

const activePath = computed(() => {
  if (route.path.startsWith('/shops/edit')) {
    return '/shops';
  }

  return route.path;
});

async function handleSelect(path: string): Promise<void> {
  await router.push(path);
}
</script>

<style scoped>
.sidebar {
  min-height: 100vh;
  padding: 28px 18px;
  background:
    linear-gradient(180deg, rgba(8, 21, 43, 0.96) 0%, rgba(18, 37, 73, 0.96) 100%),
    radial-gradient(circle at top, rgba(79, 145, 255, 0.32), transparent 28%);
  color: #fff;
}

.sidebar__brand {
  padding: 10px 14px 24px;
}

.sidebar__brand h1 {
  margin: 8px 0 6px;
  font-size: 28px;
  line-height: 1.1;
}

.sidebar__brand span {
  display: block;
  color: rgba(220, 230, 245, 0.78);
}

.sidebar__menu {
  border-right: 0;
}

.sidebar__menu-item {
  margin-bottom: 6px;
  border-radius: 14px;
}

.sidebar__menu-item.is-active {
  background: rgba(255, 255, 255, 0.14);
}

@media (max-width: 960px) {
  .sidebar {
    min-height: auto;
    padding-bottom: 16px;
  }
}
</style>
