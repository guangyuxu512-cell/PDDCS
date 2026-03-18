<template>
  <section class="shop-manage">
    <el-tabs v-model="activePlatform" class="shop-manage__tabs">
      <el-tab-pane v-for="platform in platformOrder" :key="platform" :name="platform">
        <template #label>
          <div class="shop-manage__tab-label">
            <span>{{ platformLabel[platform] }}</span>
            <el-badge :value="shopCountByPlatform[platform]" />
          </div>
        </template>

        <el-skeleton :loading="loading" animated>
          <template #template>
            <div class="shop-manage__grid">
              <el-card v-for="item in 3" :key="item" class="shop-manage__skeleton-card">
                <el-skeleton-item style="width: 52%; height: 26px" variant="text" />
                <div class="shop-manage__skeleton-meta">
                  <el-skeleton-item style="width: 72px; height: 24px" variant="button" />
                  <el-skeleton-item style="width: 64px; height: 14px" variant="text" />
                </div>
                <el-skeleton-item style="width: 100%; height: 74px" variant="p" />
              </el-card>
            </div>
          </template>

          <div v-if="platformShops[platform].length" class="shop-manage__grid">
            <ShopCard
              v-for="shop in platformShops[platform]"
              :key="shop.id"
              :shop="shop"
              @edit="handleEdit"
              @toggle-ai="handleToggleAi"
              @toggle-status="handleToggleStatus"
            />
          </div>
          <el-empty v-else description="当前平台暂无店铺" />
        </el-skeleton>
      </el-tab-pane>
    </el-tabs>

    <div class="shop-manage__footer">
      <el-button round size="large" type="primary" @click="openAddDialog">添加店铺</el-button>
    </div>
    <ShopEditDialog
      v-model="dialogVisible"
      :shop-id="selectedShopId"
      @saved="handleConfigSaved"
    />
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, onMounted, ref } from 'vue';

import { fetchShopList, toggleShopAi, toggleShopStatus } from '@/api/shop';
import ShopCard from '@/components/ShopCard.vue';
import ShopEditDialog from '@/components/ShopEditDialog.vue';
import { platformLabel, type Platform, type Shop } from '@/types/shop';
import type { ShopConfig } from '@/types/shopConfig';

const platformOrder: Platform[] = ['pdd', 'douyin', 'qianniu'];

const loading = ref(true);
const activePlatform = ref<Platform>('pdd');
const shops = ref<Shop[]>([]);
const dialogVisible = ref(false);
const selectedShopId = ref<string | null>(null);

const platformShops = computed<Record<Platform, Shop[]>>(() => ({
  pdd: shops.value.filter((shop) => shop.platform === 'pdd'),
  douyin: shops.value.filter((shop) => shop.platform === 'douyin'),
  qianniu: shops.value.filter((shop) => shop.platform === 'qianniu'),
}));

const shopCountByPlatform = computed<Record<Platform, number>>(() => ({
  pdd: platformShops.value.pdd.length,
  douyin: platformShops.value.douyin.length,
  qianniu: platformShops.value.qianniu.length,
}));

onMounted(async () => {
  await loadShops();
});

async function loadShops(): Promise<void> {
  loading.value = true;
  try {
    shops.value = await fetchShopList();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '店铺列表加载失败');
  } finally {
    loading.value = false;
  }
}

function openAddDialog(): void {
  ElMessage.info('添加店铺功能待接入');
}

function handleEdit(shopId: string): void {
  selectedShopId.value = shopId;
  dialogVisible.value = true;
}

async function handleToggleAi(shopId: string, enabled: boolean): Promise<void> {
  try {
    const updatedShop = await toggleShopAi(shopId, enabled);
    replaceShop(updatedShop);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'AI 开关更新失败');
  }
}

async function handleToggleStatus(shopId: string): Promise<void> {
  try {
    const updatedShop = await toggleShopStatus(shopId);
    replaceShop(updatedShop);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '店铺状态更新失败');
  }
}

function replaceShop(updatedShop: Shop): void {
  shops.value = shops.value.map((shop) => (shop.id === updatedShop.id ? updatedShop : shop));
}

function handleConfigSaved(config: ShopConfig): void {
  shops.value = shops.value.map((shop) =>
    shop.id === config.shopId
      ? {
          ...shop,
          name: config.name,
          aiEnabled: config.aiEnabled,
          cookieValid: config.cookieValid,
          platform: config.platform,
        }
      : shop,
  );
}
</script>

<style scoped>
.shop-manage {
  display: grid;
  gap: 20px;
}

.shop-manage__tabs {
  padding: 24px;
  border: 1px solid rgba(99, 123, 160, 0.18);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 48px rgba(17, 38, 66, 0.08);
}

.shop-manage__tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.shop-manage__tab-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.shop-manage__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.shop-manage__skeleton-card {
  border-radius: 24px;
}

.shop-manage__skeleton-meta {
  display: flex;
  gap: 12px;
  margin: 16px 0;
}

.shop-manage__footer {
  display: flex;
  justify-content: center;
}

@media (max-width: 1180px) {
  .shop-manage__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .shop-manage__tabs {
    padding: 18px 16px;
  }

  .shop-manage__grid {
    grid-template-columns: 1fr;
  }
}
</style>
