<template>
  <section class="page">
    <div class="page__hero">
      <div>
        <p class="page__eyebrow">Dashboard</p>
        <h3>总览仪表盘</h3>
        <p>Step 1 先完成导航骨架，后续步骤再接入统计卡片、趋势图和实时告警。</p>
      </div>
      <el-tag type="primary" size="large">布局已接通</el-tag>
    </div>

    <div class="page__panel">
      <span>当前页面用于验证路由切换、布局挂载和空白内容区渲染。</span>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: grid;
  gap: 18px;
}

.page__hero,
.page__panel {
  padding: 24px;
  border: 1px solid rgba(99, 123, 160, 0.18);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 48px rgba(17, 38, 66, 0.08);
}

.page__hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page__hero h3 {
  margin: 8px 0;
  font-size: 30px;
}

.page__hero p {
  margin: 0;
  color: #4f647e;
}

.page__eyebrow {
  color: #5b7795;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.page__panel {
  min-height: 220px;
  color: #516984;
}

@media (max-width: 768px) {
  .page__hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
