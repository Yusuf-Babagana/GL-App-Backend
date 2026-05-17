import type { CartSyncResponse, SyncPayload } from '../types/cart';

const API_BASE = 'https://glappbackend.pythonanywhere.com/api/market';

class CartApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'CartApiError';
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    const body = await response.text();
    throw new CartApiError(
      body || `Request failed with status ${response.status}`,
      response.status,
    );
  }

  return response.json();
}

export async function syncCart(
  token: string,
  payload: SyncPayload,
): Promise<CartSyncResponse> {
  return request<CartSyncResponse>('/cart/sync/', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchCart(token: string): Promise<any> {
  return request<any>('/cart/', token, { method: 'GET' });
}

export async function addCartItem(
  token: string,
  productId: number,
  quantity: number = 1,
): Promise<any> {
  return request<any>('/cart/', token, {
    method: 'POST',
    body: JSON.stringify({ product_id: productId, quantity }),
  });
}

export async function removeCartItem(token: string, itemId: number): Promise<any> {
  return request<any>('/cart/', token, {
    method: 'DELETE',
    body: JSON.stringify({ item_id: itemId }),
  });
}
