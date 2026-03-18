import axios, { AxiosError, type AxiosResponse } from 'axios';

import type { ApiResponse } from '@/types/api';

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10000,
});

request.interceptors.response.use(
  (response: AxiosResponse<ApiResponse<unknown>>) => {
    if (response.data.code !== 0) {
      return Promise.reject(new Error(response.data.msg || 'Request failed'));
    }

    return response;
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    const message = error.response?.data?.msg ?? error.message ?? 'Network Error';
    return Promise.reject(new Error(message));
  },
);

export async function unwrapResponse<T>(
  promise: Promise<AxiosResponse<ApiResponse<T>>>,
): Promise<T> {
  const response = await promise;
  return response.data.data;
}

export default request;
