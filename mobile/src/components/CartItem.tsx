import React from 'react';
import {
  View,
  Text,
  Image,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import type { SyncedCartItem } from '../types/cart';

interface CartItemProps {
  item: SyncedCartItem;
  onIncrement: () => void;
  onDecrement: () => void;
  onRemove: () => void;
}

const CartItemComponent: React.FC<CartItemProps> = ({
  item,
  onIncrement,
  onDecrement,
  onRemove,
}) => {
  const hasWarning = !!item.stock_warning;
  const isOutOfStock = item.stock_available === 0;
  const isPartiallyAvailable =
    item.synced_quantity < item.quantity && item.stock_available > 0;

  return (
    <View
      style={[
        styles.container,
        isOutOfStock && styles.outOfStockContainer,
      ]}>
      <Image
        source={{ uri: item.image || undefined }}
        style={styles.image}
        defaultSource={require('../assets/placeholder.png')}
      />

      <View style={styles.details}>
        <Text style={styles.name} numberOfLines={2}>
          {item.name}
        </Text>

        <Text style={styles.price}>₦{parseFloat(item.price).toLocaleString()}</Text>

        {hasWarning && (
          <View style={styles.warningBadge}>
            <Text style={styles.warningText}>{item.stock_warning}</Text>
          </View>
        )}

        {isPartiallyAvailable && (
          <Text style={styles.partialNote}>
            Requested {item.quantity}, synced {item.synced_quantity}
          </Text>
        )}

        {!isOutOfStock && (
          <View style={styles.quantityRow}>
            <TouchableOpacity
              style={styles.qtyButton}
              onPress={onDecrement}
              disabled={item.synced_quantity <= 1}>
              <Text style={styles.qtyButtonText}>−</Text>
            </TouchableOpacity>

            <Text style={styles.quantity}>{item.synced_quantity}</Text>

            <TouchableOpacity
              style={styles.qtyButton}
              onPress={onIncrement}
              disabled={item.synced_quantity >= item.stock_available}>
              <Text
                style={[
                  styles.qtyButtonText,
                  item.synced_quantity >= item.stock_available &&
                    styles.qtyButtonDisabled,
                ]}>
                +
              </Text>
            </TouchableOpacity>
          </View>
        )}

        <Text style={styles.subtotal}>
          Subtotal: ₦{parseFloat(item.subtotal).toLocaleString()}
        </Text>
      </View>

      <TouchableOpacity style={styles.removeButton} onPress={onRemove}>
        <Text style={styles.removeText}>✕</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    marginHorizontal: 16,
    marginVertical: 6,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  outOfStockContainer: {
    opacity: 0.6,
  },
  image: {
    width: 80,
    height: 80,
    borderRadius: 8,
    backgroundColor: '#f0f0f0',
  },
  details: {
    flex: 1,
    marginLeft: 12,
    justifyContent: 'center',
  },
  name: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  price: {
    fontSize: 16,
    fontWeight: '700',
    color: '#2e7d32',
    marginBottom: 4,
  },
  warningBadge: {
    backgroundColor: '#fff3e0',
    borderRadius: 4,
    paddingHorizontal: 8,
    paddingVertical: 2,
    alignSelf: 'flex-start',
    marginBottom: 4,
  },
  warningText: {
    fontSize: 11,
    color: '#e65100',
    fontWeight: '500',
  },
  partialNote: {
    fontSize: 11,
    color: '#9e9e9e',
    fontStyle: 'italic',
    marginBottom: 4,
  },
  quantityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
  },
  qtyButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#f5f5f5',
    justifyContent: 'center',
    alignItems: 'center',
  },
  qtyButtonText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
  },
  qtyButtonDisabled: {
    color: '#ccc',
  },
  quantity: {
    fontSize: 16,
    fontWeight: '600',
    marginHorizontal: 16,
    minWidth: 24,
    textAlign: 'center',
  },
  subtotal: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  removeButton: {
    padding: 8,
    justifyContent: 'flex-start',
  },
  removeText: {
    fontSize: 16,
    color: '#b71c1c',
  },
});

export default CartItemComponent;
