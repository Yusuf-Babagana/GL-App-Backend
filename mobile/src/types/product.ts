export interface Product {
  id: number;
  name: string;
  price: string;
  image: string | null;
  images: { id: number; image: string; is_primary: boolean }[];
  video: string | null;
  stock: number;
  description: string;
  currency: string;
  is_ad: boolean;
  average_rating: string;
  shop: number;
  category: number;
  created_at: string;
  seller_id: number;
  shop_name: string;
}

export interface PaginatedResponse<T> {
  count: number;
  total_pages: number;
  page: number;
  page_size: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
