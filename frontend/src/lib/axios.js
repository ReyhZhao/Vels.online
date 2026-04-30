import axios from 'axios';

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[2]) : null;
}

const MUTATING_METHODS = ['post', 'put', 'patch', 'delete'];

export function attachCsrfToken(config) {
  if (MUTATING_METHODS.includes(config.method?.toLowerCase())) {
    config.headers['X-CSRFToken'] = getCookie('csrftoken');
  }
  return config;
}

const api = axios.create({ withCredentials: true });
api.interceptors.request.use(attachCsrfToken);

export default api;
