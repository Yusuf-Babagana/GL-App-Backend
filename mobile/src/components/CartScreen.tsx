import React, { useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  ActivityIndicator,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { useCartStore } from '../store/cartStore';
import CartItemComponent from './CartItem';
import type { SyncedCartItem } from '../types/cart';

interface CartScreenProps {
  token: string;
  onCheckout: () => void;
  onBack: () => void;
}

const CartScreen: React.FC<CartScreenProps> = ({ token, onCheckout, onBack }) => {
  const {
    localItems,
    syncedItems,
    totalPrice,
    isSyncing,
    syncWithBackend,
    loadFromBackend,
    updateQuantity,
    removeItem,
  } = useCartStore();

  useEffect(() => {
    loadFromBackend(token);
  }, []);

  const handleSync = useCallback(async () => {
    const response = await syncWithBackend(token);
    if (!response) {
      console.warn('Sync failed — displaying local cart data');
    }
  }, [token, syncWithBackend]);

  const handleIncrement = useCallback(
    (productId: number) => {
      updateQuantity(productId, getLocalQty(productId) + 1);
    },
    [updateQuantity],
  );

  const handleDecrement = useCallback(
    (productId: number) => {
      const current = getLocalQty(productId);
      if (current <= 1) {
        removeItem(productId);
      } else {
        updateQuantity(productId, current - 1);
      }
    },
    [updateQuantity, removeItem],
  );

  const getLocalQty = (productId: number): number => {
    const found = localItems.find((i) => i.product_id === productId);
    return found?.quantity ?? 0;
  };

  const displayItems: SyncedCartItem[] =
    syncedItems.length > 0
      ? syncedItems
      : localItems.map((li) => ({
          product_id: li.product_id,
          quantity: li.quantity,
          synced_quantity: li.quantity,
          name: li.name || `Product #${li.product_id}`,
          price: String(li.price ?? 0),
          image: li.image ?? null,
          stock_available: li.stock_available ?? 0,
          stock_warning: null,
          subtotal: String((li.price ?? 0) * li.quantity),
        }));

  const hasStockIssues = displayItems.some((i) => !!i.stock_warning);
  const isEmpty = displayItems.length === 0;

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onBack}>
          <Text style={styles.backButton}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Cart</Text>
        <TouchableOpacity onPress={handleSync} disabled={isSyncing}>
          <Text style={styles.syncButton}>{isSyncing ? '...' : 'Sync'}</Text>
        </TouchableOpacity>
      </View>

      {isEmpty && !isSyncing && (
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>Your cart is empty</Text>
        </View>
      )}

      <FlatList
        data={displayItems}
        keyExtractor={(item) => String(item.product_id)}
        renderItem={({ item }) => (
          <CartItemComponent
            item={item}
            onIncrement={() => handleIncrement(item.product_id)}
            onDecrement={() => handleDecrement(item.product_id)}
            onRemove={() => removeItem(item.product_id)}
          />
        )}
        contentContainerStyle={styles.list}
        refreshing={isSyncing}
        onRefresh={handleSync}
      />

      {!isEmpty && (
        <View style={styles.footer}>
          {hasStockIssues && (
            <View style={styles.footerWarning}>
              <Text style={styles.footerWarningText}>
                Some items have stock changes — review before checkout
              </Text>
            </View>
          )}

          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Total</Text>
            <Text style={styles.totalAmount}>
              ₦{totalPrice.toLocaleString(undefined, {
                minimumFractionDigits: 2,
              })}
            </Text>
          </View>

          <TouchableOpacity
            style={[
              styles.checkoutButton,
              (isSyncing || hasStockIssues) && styles.checkoutButtonDisabled,
            ]}
            onPress={onCheckout}
            disabled={isSyncing || hasStockIssues}>
            {isSyncing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.checkoutText}>Proceed to Checkout</Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  backButton: {
    fontSize: 16,
    color: '#1976d2',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  syncButton: {
    fontSize: 16,
    color: '#1976d2',
    fontWeight: '600',
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
  },
  list: {
    paddingVertical: 8,
  },
  footer: {
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: '#eee',
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: -4,
    elevation: -2,
  },
  footerWarning: {
    backgroundColor: '#fff3e0',
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
  },
  footerWarningText: {
    fontSize: 12,
    color: '#e65100',
    textAlign: 'center',
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  totalLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
  },
  totalAmount: {
    fontSize: 22,
    fontWeight: '800',
    color: '#1a1a1a',
  },
  checkoutButton: {
    backgroundColor: '#2e7d32',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
  },
  checkoutButtonDisabled: {
    backgroundColor: '#a5d6a7',
  },
  checkoutText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});

export default CartScreen;
