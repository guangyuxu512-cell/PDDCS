import type { MockMethod } from 'vite-plugin-mock';

import type { KnowledgeDocument, KnowledgeTreeNode } from '@/types/knowledge';

interface KnowledgeRequest {
  body?: {
    path?: string;
    content?: string;
    parentPath?: string;
    name?: string;
  };
  query?: {
    path?: string;
  };
}

let documents: Record<string, KnowledgeDocument> = {
  'global/发货说明.md': {
    path: 'global/发货说明.md',
    content: '# 发货说明\n\n- 默认 24 小时内发货\n- 大促期间顺延 1-2 天\n',
    updatedAt: '2026-03-19T09:20:00+08:00',
  },
  'global/售后政策.md': {
    path: 'global/售后政策.md',
    content: '# 售后政策\n\n收到商品后 7 天内支持申请退换货。\n',
    updatedAt: '2026-03-18T18:40:00+08:00',
  },
  'shops/拼多多旗舰店/活动规则.md': {
    path: 'shops/拼多多旗舰店/活动规则.md',
    content: '# 活动规则\n\n- 满 199 减 20\n- 新客首单包邮\n',
    updatedAt: '2026-03-19T08:55:00+08:00',
  },
  'shops/抖店服饰专营/尺码建议.md': {
    path: 'shops/抖店服饰专营/尺码建议.md',
    content: '# 尺码建议\n\n根据身高体重优先推荐，避免绝对化承诺。\n',
    updatedAt: '2026-03-19T09:03:00+08:00',
  },
  'shops/千牛家居馆/安装说明.md': {
    path: 'shops/千牛家居馆/安装说明.md',
    content: '# 安装说明\n\n随包裹附带安装配件与视频二维码。\n',
    updatedAt: '2026-03-19T07:48:00+08:00',
  },
};

function folderNode(name: string, path: string): KnowledgeTreeNode {
  return { id: `folder:${path}`, name, path, nodeType: 'folder', children: [] };
}

function fileNode(name: string, path: string): KnowledgeTreeNode {
  return { id: `file:${path}`, name, path, nodeType: 'file' };
}

function buildTree(): KnowledgeTreeNode[] {
  const root: KnowledgeTreeNode[] = [];

  for (const path of Object.keys(documents)) {
    const parts = path.split('/');
    let currentLevel = root;
    let currentPath = '';

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isFile = index === parts.length - 1;
      let existing = currentLevel.find((node) => node.path === currentPath);

      if (!existing) {
        existing = isFile ? fileNode(part, currentPath) : folderNode(part, currentPath);
        currentLevel.push(existing);
      }

      if (!isFile) {
        existing.children ??= [];
        currentLevel = existing.children;
      }
    });
  }

  function sortNodes(nodes: KnowledgeTreeNode[]): KnowledgeTreeNode[] {
    return nodes
      .slice()
      .sort((left, right) => {
        if (left.nodeType !== right.nodeType) {
          return left.nodeType === 'folder' ? -1 : 1;
        }
        return left.name.localeCompare(right.name, 'zh-CN');
      })
      .map((node) =>
        node.nodeType === 'folder'
          ? { ...node, children: sortNodes(node.children ?? []) }
          : node,
      );
  }

  return sortNodes(root);
}

const knowledgeMocks: MockMethod[] = [
  {
    url: '/api/knowledge/tree',
    method: 'get',
    response: () => ({
      code: 0,
      msg: 'success',
      data: buildTree(),
    }),
  },
  {
    url: '/api/knowledge/document',
    method: 'get',
    response: ({ query }: KnowledgeRequest) => {
      const path = query?.path ?? '';
      const document = documents[path];
      return {
        code: document ? 0 : 404,
        msg: document ? 'success' : 'document not found',
        data: document ?? null,
      };
    },
  },
  {
    url: '/api/knowledge/document',
    method: 'put',
    response: ({ body }: KnowledgeRequest) => {
      const path = body?.path ?? '';
      if (!documents[path]) {
        return { code: 404, msg: 'document not found', data: null };
      }
      documents[path] = {
        path,
        content: body?.content ?? '',
        updatedAt: new Date().toISOString(),
      };
      return {
        code: 0,
        msg: 'success',
        data: documents[path],
      };
    },
  },
  {
    url: '/api/knowledge/document',
    method: 'post',
    response: ({ body }: KnowledgeRequest) => {
      const parentPath = body?.parentPath ?? 'global';
      const name = body?.name ?? `新建文件-${Date.now()}.md`;
      const path = `${parentPath}/${name}`;
      documents[path] = {
        path,
        content: `# ${name.replace(/\.md$/i, '')}\n\n`,
        updatedAt: new Date().toISOString(),
      };
      return {
        code: 0,
        msg: 'success',
        data: documents[path],
      };
    },
  },
  {
    url: '/api/knowledge/document',
    method: 'delete',
    response: ({ body }: KnowledgeRequest) => {
      const path = body?.path ?? '';
      delete documents[path];
      return {
        code: 0,
        msg: 'success',
        data: { path },
      };
    },
  },
];

export default knowledgeMocks;
