<template>
  <section class="knowledge">
    <aside class="knowledge__sidebar">
      <div class="knowledge__toolbar">
        <el-button plain type="primary" @click="handleCreateFile">新增文件</el-button>
        <el-button plain type="danger" @click="handleDeleteFile">删除文件</el-button>
      </div>
      <el-scrollbar class="knowledge__tree-scroll">
        <el-tree
          :current-node-key="selectedPath"
          :data="treeData"
          :expand-on-click-node="false"
          :highlight-current="true"
          :props="treeProps"
          node-key="path"
          @node-click="handleNodeClick"
        />
      </el-scrollbar>
    </aside>

    <section class="knowledge__editor-pane">
      <header class="knowledge__header">
        <div>
          <span class="knowledge__path-label">当前文件路径</span>
          <strong>{{ selectedPath || '未选择文件' }}</strong>
        </div>
        <el-button :disabled="!currentDocument" type="primary" @click="handleSave">保存</el-button>
      </header>

      <el-input
        v-model="editorContent"
        :autosize="{ minRows: 18, maxRows: 28 }"
        class="knowledge__editor"
        placeholder="请选择左侧 Markdown 文件进行编辑"
        resize="none"
        type="textarea"
      />

      <footer class="knowledge__status">
        最后保存时间：{{ lastSavedText }}
      </footer>
    </section>
  </section>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, ref } from 'vue';

import {
  createKnowledgeDocument,
  deleteKnowledgeDocument,
  fetchKnowledgeDocument,
  fetchKnowledgeTree,
  saveKnowledgeDocument,
} from '@/api/knowledge';
import type { KnowledgeDocument, KnowledgeTreeNode } from '@/types/knowledge';

const treeData = ref<KnowledgeTreeNode[]>([]);
const selectedPath = ref('');
const currentDocument = ref<KnowledgeDocument | null>(null);
const editorContent = ref('');

const treeProps = {
  children: 'children',
  label: 'name',
} as const;

const lastSavedText = computed(() =>
  currentDocument.value?.updatedAt
    ? new Date(currentDocument.value.updatedAt).toLocaleString('zh-CN')
    : '--',
);

onMounted(async () => {
  await loadTree();
});

async function loadTree(preferredPath?: string): Promise<void> {
  try {
    const tree = await fetchKnowledgeTree();
    treeData.value = tree;
    const nextPath = preferredPath || selectedPath.value || findFirstFilePath(tree);
    if (nextPath) {
      await loadDocument(nextPath);
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '知识库目录加载失败');
  }
}

async function loadDocument(path: string): Promise<void> {
  try {
    const document = await fetchKnowledgeDocument(path);
    currentDocument.value = document;
    editorContent.value = document.content;
    selectedPath.value = document.path;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '知识库文件加载失败');
  }
}

async function handleNodeClick(node: KnowledgeTreeNode): Promise<void> {
  if (node.nodeType !== 'file') {
    return;
  }
  await loadDocument(node.path);
}

async function handleSave(): Promise<void> {
  if (!currentDocument.value) {
    return;
  }

  try {
    const saved = await saveKnowledgeDocument(currentDocument.value.path, editorContent.value);
    currentDocument.value = saved;
    editorContent.value = saved.content;
    ElMessage.success('知识库内容已保存');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '知识库保存失败');
  }
}

async function handleCreateFile(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的 Markdown 文件名', '新增文件', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：售后FAQ.md',
    });

    const parentPath = resolveTargetFolderPath(selectedPath.value, treeData.value);
    const created = await createKnowledgeDocument(parentPath, ensureMarkdownFilename(value));
    await loadTree(created.path);
    ElMessage.success('文件已创建');
  } catch {
    return;
  }
}

async function handleDeleteFile(): Promise<void> {
  if (!currentDocument.value) {
    ElMessage.info('请先选择一个 Markdown 文件');
    return;
  }

  try {
    await ElMessageBox.confirm(`确定删除 ${currentDocument.value.path} 吗？`, '删除文件', {
      type: 'warning',
    });
    await deleteKnowledgeDocument(currentDocument.value.path);
    currentDocument.value = null;
    editorContent.value = '';
    selectedPath.value = '';
    await loadTree();
    ElMessage.success('文件已删除');
  } catch {
    return;
  }
}

function ensureMarkdownFilename(value: string): string {
  const trimmed = value.trim() || `新建文件-${Date.now()}`;
  return trimmed.endsWith('.md') ? trimmed : `${trimmed}.md`;
}

function resolveTargetFolderPath(path: string, nodes: KnowledgeTreeNode[]): string {
  const target = findNodeByPath(nodes, path);
  if (!target) {
    return 'global';
  }
  if (target.nodeType === 'folder') {
    return target.path;
  }
  const parts = target.path.split('/');
  parts.pop();
  return parts.join('/');
}

function findNodeByPath(nodes: KnowledgeTreeNode[], path: string): KnowledgeTreeNode | null {
  for (const node of nodes) {
    if (node.path === path) {
      return node;
    }
    if (node.children?.length) {
      const matched = findNodeByPath(node.children, path);
      if (matched) {
        return matched;
      }
    }
  }
  return null;
}

function findFirstFilePath(nodes: KnowledgeTreeNode[]): string {
  for (const node of nodes) {
    if (node.nodeType === 'file') {
      return node.path;
    }
    if (node.children?.length) {
      const childPath = findFirstFilePath(node.children);
      if (childPath) {
        return childPath;
      }
    }
  }
  return '';
}
</script>

<style scoped>
.knowledge {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 18px;
  min-height: 720px;
}

.knowledge__sidebar,
.knowledge__editor-pane {
  display: grid;
  gap: 16px;
  padding: 20px;
  border: 1px solid rgba(99, 123, 160, 0.18);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 48px rgba(17, 38, 66, 0.08);
}

.knowledge__sidebar {
  grid-template-rows: auto minmax(0, 1fr);
}

.knowledge__toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.knowledge__tree-scroll {
  min-height: 0;
}

.knowledge__editor-pane {
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.knowledge__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.knowledge__path-label,
.knowledge__status {
  color: #66788e;
  font-size: 14px;
}

.knowledge__header strong {
  display: block;
  margin-top: 6px;
  color: #152238;
}

.knowledge__editor :deep(textarea) {
  min-height: 520px;
  font-family: 'Consolas', 'Courier New', monospace;
  line-height: 1.6;
}

@media (max-width: 960px) {
  .knowledge {
    grid-template-columns: 1fr;
  }
}
</style>
