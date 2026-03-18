<template>
  <el-container class="app-layout">
    <Sidebar class="app-layout__sidebar" />
    <el-container class="app-layout__shell">
      <el-main class="app-layout__main">
        <RouterView v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import Sidebar from '@/components/layout/Sidebar.vue';
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: transparent;
}

.app-layout__sidebar {
  width: 264px;
  flex: 0 0 264px;
}

.app-layout__shell {
  min-width: 0;
}

.app-layout__main {
  padding: 24px;
  padding-top: 24px;
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 960px) {
  .app-layout {
    flex-direction: column;
  }

  .app-layout__sidebar {
    width: 100%;
    flex-basis: auto;
  }

  .app-layout__main {
    padding: 16px;
  }
}
</style>
