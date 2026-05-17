import type { Product, PaginatedResponse } from '../types/product';

const API_BASE = 'https://glappbackend.pythonanywhere.com/api/market';

export async function fetchProducts(
  page: number = 1,
  pageSize: number = 20,
  search?: string,
): Promise<PaginatedResponse<Product>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (search) {
    params.set('search', search);
  }

  const response = await fetch(`${API_BASE}/products/?${params.toString()}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch products: ${response.status}`);
  }
  return response.json();
}

export async function fetchVideoAds(page: number = 1): Promise<PaginatedResponse<Product>> {
  const response = await fetch(
    `${API_BASE}/video-ads/?page=${page}&page_size=10`,
    { headers: { 'Content-Type': 'application/json' } },
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch video ads: ${response.status}`);
  }
  return response.json();
}
