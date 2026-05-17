import React, { useEffect, useCallback, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  SafeAreaView,
  TextInput,
} from 'react-native';
import { fetchProducts } from '../services/productService';
import type { Product, PaginatedResponse } from '../types/product';

interface ProductListScreenProps {
  onProductPress: (product: Product) => void;
}

const ProductListScreen: React.FC<ProductListScreenProps> = ({ onProductPress }) => {
  const [products, setProducts] = useState<Product[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (pageNum: number, refresh: boolean = false) => {
      if (refresh) {
        setIsRefreshing(true);
      } else if (pageNum === 1) {
        setIsLoading(true);
      } else {
        setIsLoadingMore(true);
      }
      setError(null);

      try {
        const data: PaginatedResponse<Product> = await fetchProducts(
          pageNum,
          20,
          search || undefined,
        );

        if (refresh || pageNum === 1) {
          setProducts(data.results);
        } else {
          setProducts((prev) => [...prev, ...data.results]);
        }
        setPage(pageNum);
        setTotalPages(data.total_pages);
      } catch (err: any) {
        setError(err.message || 'Failed to load products');
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
        setIsLoadingMore(false);
      }
    },
    [search],
  );

  useEffect(() => {
    loadPage(1);
  }, []);

  const handleRefresh = useCallback(() => {
    loadPage(1, true);
  }, [loadPage]);

  const handleEndReached = useCallback(() => {
    if (isLoadingMore || page >= totalPages) return;
    loadPage(page + 1);
  }, [page, totalPages, isLoadingMore, loadPage]);

  const handleSearch = useCallback(() => {
    loadPage(1);
  }, [loadPage]);

  const renderProduct = useCallback(
    ({ item }: { item: Product }) => (
      <TouchableOpacity
        style={styles.productCard}
        onPress={() => onProductPress(item)}
        activeOpacity={0.8}>
        <Image
          source={{ uri: item.image || undefined }}
          style={styles.productImage}
          defaultSource={require('../assets/placeholder.png')}
        />
        <View style={styles.productInfo}>
          <Text style={styles.shopName} numberOfLines={1}>
            {item.shop_name}
          </Text>
          <Text style={styles.productName} numberOfLines={2}>
            {item.name}
          </Text>
          <Text style={styles.productPrice}>
            ₦{parseFloat(item.price).toLocaleString()}
          </Text>
          {item.stock <= 5 && item.stock > 0 && (
            <Text style={styles.lowStock}>Only {item.stock} left</Text>
          )}
          {item.stock === 0 && (
            <Text style={styles.outOfStock}>Out of stock</Text>
          )}
        </View>
      </TouchableOpacity>
    ),
    [onProductPress],
  );

  const renderFooter = () => {
    if (!isLoadingMore) return null;
    return (
      <View style={styles.footerLoader}>
        <ActivityIndicator size="small" color="#1976d2" />
        <Text style={styles.footerText}>Loading more...</Text>
      </View>
    );
  };

  const renderEmpty = () => {
    if (isLoading) return null;
    return (
      <View style={styles.emptyState}>
        <Text style={styles.emptyText}>
          {error ? error : 'No products found'}
        </Text>
      </View>
    );
  };

  if (isLoading && products.length === 0) {
    return (
      <SafeAreaView style={styles.screen}>
        <View style={styles.headerLoader}>
          <ActivityIndicator size="large" color="#1976d2" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.searchBar}>
        <TextInput
          style={styles.searchInput}
          placeholder="Search products..."
          value={search}
          onChangeText={setSearch}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
        />
      </View>

      <FlatList
        data={products}
        renderItem={renderProduct}
        keyExtractor={(item) => String(item.id)}
        numColumns={2}
        contentContainerStyle={styles.list}
        columnWrapperStyle={styles.row}
        onEndReached={handleEndReached}
        onEndReachedThreshold={0.5}
        refreshing={isRefreshing}
        onRefresh={handleRefresh}
        ListFooterComponent={renderFooter}
        ListEmptyComponent={renderEmpty}
      />

      {page < totalPages && products.length > 0 && (
        <View style={styles.pageIndicator}>
          <Text style={styles.pageText}>
            Page {page} of {totalPages}
          </Text>
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
  headerLoader: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchBar: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  searchInput: {
    backgroundColor: '#f0f0f0',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
  },
  list: {
    paddingHorizontal: 8,
    paddingTop: 8,
  },
  row: {
    justifyContent: 'space-between',
  },
  productCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    marginBottom: 12,
    width: '48%',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  productImage: {
    width: '100%',
    height: 140,
    backgroundColor: '#f0f0f0',
    resizeMode: 'cover',
  },
  productInfo: {
    padding: 10,
  },
  shopName: {
    fontSize: 11,
    color: '#999',
    fontWeight: '500',
    marginBottom: 2,
  },
  productName: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  productPrice: {
    fontSize: 15,
    fontWeight: '700',
    color: '#2e7d32',
  },
  lowStock: {
    fontSize: 11,
    color: '#e65100',
    fontWeight: '500',
    marginTop: 2,
  },
  outOfStock: {
    fontSize: 11,
    color: '#b71c1c',
    fontWeight: '600',
    marginTop: 2,
  },
  footerLoader: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
  },
  footerText: {
    marginLeft: 8,
    fontSize: 13,
    color: '#666',
  },
  emptyState: {
    paddingVertical: 60,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 15,
    color: '#999',
  },
  pageIndicator: {
    backgroundColor: '#fff',
    paddingVertical: 6,
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#eee',
  },
  pageText: {
    fontSize: 12,
    color: '#999',
  },
});

export default ProductListScreen;
