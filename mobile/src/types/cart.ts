export interface LocalCartItem {
  product_id: number;
  quantity: number;
  name?: string;
  price?: number;
  image?: string | null;
  stock_available?: number;
}

export interface SyncedCartItem {
  product_id: number;
  quantity: number;
  name: string;
  price: string;
  image: string | null;
  stock_available: number;
  stock_warning: string | null;
  synced_quantity: number;
  subtotal: string;
}

export interface CartSyncResponse {
  synced_items: SyncedCartItem[];
  total_price: string;
  synced_at: string;
}

export interface SyncPayload {
  items: { product_id: number; quantity: number }[];
}
