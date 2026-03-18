import request, { unwrapResponse } from '@/api/request';
import type { ApiResponse } from '@/types/api';
import type { DashboardSummary } from '@/types/dashboard';

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return unwrapResponse(request.get<ApiResponse<DashboardSummary>>('/dashboard/summary'));
}
