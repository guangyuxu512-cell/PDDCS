import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { KnowledgeDocument, KnowledgeTreeNode } from '@/types/knowledge';

export async function fetchKnowledgeTree(): Promise<KnowledgeTreeNode[]> {
  return unwrapResponse(request.get<ApiResponse<KnowledgeTreeNode[]>>('/knowledge/tree'));
}

export async function fetchKnowledgeFileList(): Promise<string[]> {
  return unwrapResponse(request.get<ApiResponse<string[]>>('/knowledge/files'));
}

export async function fetchKnowledgeDocument(path: string): Promise<KnowledgeDocument> {
  return unwrapResponse(
    request.get<ApiResponse<KnowledgeDocument>>('/knowledge/document', {
      params: { path },
    }),
  );
}

export async function saveKnowledgeDocument(path: string, content: string): Promise<KnowledgeDocument> {
  return unwrapResponse(
    request.put<ApiResponse<KnowledgeDocument>>('/knowledge/document', {
      path,
      content,
    }),
  );
}

export async function createKnowledgeDocument(parentPath: string, name: string): Promise<KnowledgeDocument> {
  return unwrapResponse(
    request.post<ApiResponse<KnowledgeDocument>>('/knowledge/document', {
      parentPath,
      name,
    }),
  );
}

export async function deleteKnowledgeDocument(path: string): Promise<{ path: string }> {
  return unwrapResponse(
    request.delete<ApiResponse<{ path: string }>>('/knowledge/document', {
      data: { path },
    }),
  );
}
