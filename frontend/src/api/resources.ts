import type { AxiosRequestConfig } from "axios";
import { api, asPage } from "./client";
import type { Page } from "../types/api";

export async function getOne<T>(path: string, config?: AxiosRequestConfig) {
  const { data } = await api.get<T>(path, config);
  return data;
}

export async function getPage<T>(
  path: string,
  params?: Record<string, unknown>,
) {
  const { data } = await api.get<Page<T> | T[]>(path, { params });
  return asPage(data);
}

export async function postOne<TResponse, TBody = unknown>(
  path: string,
  body?: TBody,
) {
  const { data } = await api.post<TResponse>(path, body ?? {});
  return data;
}

export async function patchOne<TResponse, TBody = unknown>(
  path: string,
  body: TBody,
) {
  const { data } = await api.patch<TResponse>(path, body);
  return data;
}

export async function putOne<TResponse, TBody = unknown>(
  path: string,
  body: TBody,
) {
  const { data } = await api.put<TResponse>(path, body);
  return data;
}

export async function deleteOne(path: string) {
  await api.delete(path);
}
