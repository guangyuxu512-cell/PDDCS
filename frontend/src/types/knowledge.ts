export type KnowledgeNodeType = 'folder' | 'file';

export interface KnowledgeTreeNode {
  id: string;
  name: string;
  path: string;
  nodeType: KnowledgeNodeType;
  children?: KnowledgeTreeNode[];
}

export interface KnowledgeDocument {
  path: string;
  content: string;
  updatedAt: string;
}
