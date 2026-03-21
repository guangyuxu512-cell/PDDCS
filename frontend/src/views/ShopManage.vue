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

          <div class="shop-manage__toolbar">
            <template v-if="platform === 'pdd'">
              <el-button round type="primary" @click="openAddDialog">添加店铺</el-button>
            </template>
            <template v-else>
              <div class="shop-manage__scan-box">
                <el-button
                  plain
                  type="primary"
                  :loading="scanningWindows"
                  @click="handleScanDesktopWindows"
                >
                  扫描桌面窗口
                </el-button>
                <span class="shop-manage__scan-tip">千牛/抖店店铺通过扫描本地桌面窗口自动发现</span>
              </div>
            </template>
          </div>

          <div v-if="platformShops[platform].length" class="shop-manage__grid">
            <ShopCard
              v-for="shop in platformShops[platform]"
              :key="shop.id"
              :shop="shop"
              @delete="handleDeleteShop"
              @edit="handleEdit"
              @open-browser="handleOpenBrowser"
              @toggle-ai="handleToggleAi"
              @toggle-status="handleToggleStatus"
            />
          </div>
          <el-empty v-else description="当前平台暂无店铺" />
        </el-skeleton>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="createDialogVisible" title="添加拼多多店铺" width="420px">
      <el-form label-position="top">
        <el-form-item label="店铺名称">
          <el-input v-model="createForm.name" placeholder="请输入店铺名称" />
        </el-form-item>
        <el-form-item label="登录账号">
          <el-input v-model="createForm.username" placeholder="请输入登录账号" />
        </el-form-item>
        <el-form-item label="登录密码">
          <el-input
            v-model="createForm.password"
            placeholder="请输入登录密码"
            show-password
            type="password"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button :loading="creatingShop" type="primary" @click="handleCreateShop">确认</el-button>
      </template>
    </el-dialog>

    <ShopEditDialog
      v-model="dialogVisible"
      :shop-id="selectedShopId"
      @saved="handleConfigSaved"
    />
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';

import {
  createShop,
  deleteShop,
  fetchShopList,
  scanDesktopWindows,
  startShop,
  stopShop,
  toggleShopAi,
  toggleShopStatus,
} from '@/api/shop';
import ShopCard from '@/components/ShopCard.vue';
import ShopEditDialog from '@/components/ShopEditDialog.vue';
import { platformLabel, type Platform, type Shop } from '@/types/shop';
import type { ShopConfig } from '@/types/shopConfig';

const platformOrder: Platform[] = ['pdd', 'douyin', 'qianniu'];
const SHOP_STATUS_POLL_INTERVAL_MS = 5000;

const loading = ref(true);
const creatingShop = ref(false);
const scanningWindows = ref(false);
const activePlatform = ref<Platform>('pdd');
const shops = ref<Shop[]>([]);
const createDialogVisible = ref(false);
const dialogVisible = ref(false);
const selectedShopId = ref<string | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;
const createForm = reactive({
  name: '',
  username: '',
  password: '',
});

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
  pollTimer = setInterval(async () => {
    try {
      shops.value = await fetchShopList();
    } catch {
      // 静默忽略轮询刷新失败，避免对用户造成持续打扰。
    }
  }, SHOP_STATUS_POLL_INTERVAL_MS);
});

onUnmounted(() => {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
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
  resetCreateForm();
  createDialogVisible.value = true;
}

function handleEdit(shopId: string): void {
  selectedShopId.value = shopId;
  dialogVisible.value = true;
}

async function handleCreateShop(): Promise<void> {
  if (!createForm.name.trim() || !createForm.username.trim() || !createForm.password.trim()) {
    ElMessage.warning('请完整填写店铺信息');
    return;
  }

  creatingShop.value = true;
  try {
    await createShop({
      name: createForm.name.trim(),
      platform: 'pdd',
      username: createForm.username.trim(),
      password: createForm.password,
    });
    createDialogVisible.value = false;
    await loadShops();
    ElMessage.success('店铺创建成功');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '店铺创建失败');
  } finally {
    creatingShop.value = false;
  }
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
  const shop = shops.value.find((item) => item.id === shopId);
  if (!shop) {
    return;
  }

  try {
    if (shop.isOnline) {
      await stopShop(shopId);
      ElMessage.success('店铺已停止');
    } else {
      await startShop(shopId);
      ElMessage.success('正在启动店铺，浏览器即将打开...');
    }
    await loadShops();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '操作失败');
    await loadShops();
  }
}

async function handleDeleteShop(shopId: string): Promise<void> {
  try {
    await deleteShop(shopId);
    await loadShops();
    ElMessage.success('店铺已删除');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除店铺失败');
  }
}

async function handleOpenBrowser(shopId: string): Promise<void> {
  const shop = shops.value.find((item) => item.id === shopId);
  if (!shop) {
    return;
  }

  try {
    if (shop.isOnline) {
      ElMessage.info('店铺已在运行中，请查看浏览器窗口');
      return;
    }

    await startShop(shopId);
    ElMessage.success('正在启动店铺，浏览器即将打开...');
    await loadShops();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '启动失败');
    await loadShops();
  }
}

async function handleScanDesktopWindows(): Promise<void> {
  scanningWindows.value = true;
  try {
    const discoveredShops = await scanDesktopWindows();
    if (discoveredShops.length) {
      await loadShops();
      ElMessage.success(`扫描完成，发现 ${discoveredShops.length} 个店铺窗口`);
      return;
    }

    ElMessage.success('扫描完成，当前未发现可接管的桌面店铺窗口');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '扫描桌面窗口失败');
  } finally {
    scanningWindows.value = false;
  }
}

function replaceShop(updatedShop: Shop): void {
  shops.value = shops.value.map((shop) => (shop.id === updatedShop.id ? updatedShop : shop));
}

function resetCreateForm(): void {
  createForm.name = '';
  createForm.username = '';
  createForm.password = '';
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

.shop-manage__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.shop-manage__scan-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.shop-manage__scan-tip {
  color: #5d6f86;
  font-size: 14px;
}

.shop-manage__skeleton-card {
  border-radius: 24px;
}

.shop-manage__skeleton-meta {
  display: flex;
  gap: 12px;
  margin: 16px 0;
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

  .shop-manage__toolbar,
  .shop-manage__scan-box {
    align-items: stretch;
    flex-direction: column;
  }

  .shop-manage__grid {
    grid-template-columns: 1fr;
  }
}
</style>
