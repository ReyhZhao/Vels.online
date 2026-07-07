import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { getServerUrl } from './server';

const MUTATING_METHODS = ['post', 'put', 'patch', 'delete'];

let csrfToken: string | null = null;

export function getCsrfToken(): string | null {
  return csrfToken;
}

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

/**
 * The backend echoes the CSRF token in the X-CSRFToken response header on
 * /api/me/ (see api.views.MeView) so clients that cannot read cookies —
 * like this app — can still send it on mutating requests.
 */
export function captureCsrfFromHeaders(headers: Record<string, unknown> | undefined): void {
  const token = headers?.['x-csrftoken'];
  if (typeof token === 'string' && token) {
    csrfToken = token;
  }
}

export function attachCsrfToken(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  if (MUTATING_METHODS.includes(config.method?.toLowerCase() ?? '') && csrfToken) {
    config.headers['X-CSRFToken'] = csrfToken;
    // Django's CsrfViewMiddleware requires the Referer header on secure requests.
    config.headers['Referer'] = getServerUrl() + '/';
  }
  return config;
}

function createApi(): AxiosInstance {
  const instance = axios.create();
  instance.interceptors.request.use((config) => {
    config.baseURL = getServerUrl();
    return attachCsrfToken(config);
  });
  instance.interceptors.response.use(
    (response) => {
      captureCsrfFromHeaders(response.headers as Record<string, unknown>);
      return response;
    },
    (error) => {
      captureCsrfFromHeaders(error.response?.headers);
      return Promise.reject(error);
    },
  );
  return instance;
}

const api = createApi();

export default api;
