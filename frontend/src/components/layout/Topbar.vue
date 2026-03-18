<template>
  <header class="topbar">
    <div>
      <h2>{{ currentTitle }}</h2>
    </div>
    <div aria-hidden="true" class="topbar__spacer"></div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();

const currentTitle = computed(() => route.meta.title ?? '总览');
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 10px;
}

.topbar h2 {
  margin: 0;
  font-size: 28px;
  color: #152238;
}

.topbar__spacer {
  width: 88px;
  min-height: 1px;
}

@media (max-width: 960px) {
  .topbar {
    flex-direction: column;
    align-items: flex-start;
    padding: 18px 16px 10px;
  }
}
</style>
