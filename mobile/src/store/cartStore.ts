import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { LocalCartItem, SyncedCartItem } from '../types/cart';
import { syncCart, fetchCart } from '../services/cartService';

interface CartState {
  localItems: LocalCartItem[];
  syncedItems: SyncedCartItem[];
  totalPrice: number;
  isSyncing: boolean;
  lastSyncedAt: string | null;

  addItem: (productId: number, quantity?: number) => void;
  updateQuantity: (productId: number, quantity: number) => void;
  removeItem: (productId: number) => void;
  clearLocal: () => void;

  syncWithBackend: (token: string) => Promise<CartSyncResponse | null>;
  loadFromBackend: (token: string) => Promise<void>;
}

export const useCartStore = create<CartState>()(
  persist(
    (set, get) => ({
      localItems: [],
      syncedItems: [],
      totalPrice: 0,
      isSyncing: false,
      lastSyncedAt: null,

      addItem: (productId, quantity = 1) => {
        set((state) => {
          const existing = state.localItems.find((i) => i.product_id === productId);
          if (existing) {
            return {
              localItems: state.localItems.map((i) =>
                i.product_id === productId
                  ? { ...i, quantity: i.quantity + quantity }
                  : i,
              ),
            };
          }
          return {
            localItems: [
              ...state.localItems,
              { product_id: productId, quantity },
            ],
          };
        });
      },

      updateQuantity: (productId, quantity) => {
        set((state) => {
          if (quantity <= 0) {
            return {
              localItems: state.localItems.filter(
                (i) => i.product_id !== productId,
              ),
            };
          }
          return {
            localItems: state.localItems.map((i) =>
              i.product_id === productId ? { ...i, quantity } : i,
            ),
          };
        });
      },

      removeItem: (productId) => {
        set((state) => ({
          localItems: state.localItems.filter(
            (i) => i.product_id !== productId,
          ),
        }));
      },

      clearLocal: () => {
        set({ localItems: [], syncedItems: [], totalPrice: 0, lastSyncedAt: null });
      },

      syncWithBackend: async (token) => {
        set({ isSyncing: true });
        try {
          const payload = {
            items: get().localItems.map((i) => ({
              product_id: i.product_id,
              quantity: i.quantity,
            })),
          };
          const response = await syncCart(token, payload);
          set({
            syncedItems: response.synced_items,
            totalPrice: parseFloat(response.total_price),
            lastSyncedAt: response.synced_at,
            isSyncing: false,
          });
          return response;
        } catch (error) {
          set({ isSyncing: false });
          console.error('Cart sync failed:', error);
          return null;
        }
      },

      loadFromBackend: async (token) => {
        set({ isSyncing: true });
        try {
          const cart = await fetchCart(token);
          const localItems: LocalCartItem[] = (cart.items || []).map(
            (item: any) => ({
              product_id: item.product,
              quantity: item.quantity,
              name: item.product_name,
              price: parseFloat(item.product_price),
              image: item.product_image,
            }),
          );
          set({
            localItems,
            totalPrice: parseFloat(cart.total_price || '0'),
            isSyncing: false,
          });
        } catch (error) {
          set({ isSyncing: false });
          console.error('Failed to load cart from backend:', error);
        }
      },
    }),
    {
      name: 'globalink-cart',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        localItems: state.localItems,
        lastSyncedAt: state.lastSyncedAt,
      }),
    },
  ),
);
