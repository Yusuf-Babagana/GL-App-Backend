from rest_framework import serializers
from .models import Category, Store, Product, ProductImage, Order, OrderItem, Cart, CartItem

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon']

class StoreSerializer(serializers.ModelSerializer):
    # Explicitly expose the owner's ID for the Chat System
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = Store
        fields = ['id', 'owner', 'owner_id', 'owner_name', 'name', 'description', 'logo', 'rating', 'total_sales']
        read_only_fields = ['owner', 'rating', 'total_sales']

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary']

        
class ProductSerializer(serializers.ModelSerializer):
    store = StoreSerializer(read_only=True) 
    images = ProductImageSerializer(many=True, read_only=True)
    
    # Receive URL from mobile app
    cloudinary_url = serializers.URLField(write_only=True, required=False)

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'category', 'name', 'description', 
            'price', 'currency', 'stock', 'video', 'images', 
            'cloudinary_url', 'average_rating', 'total_reviews', 'created_at'
        ]
        read_only_fields = ['store', 'average_rating', 'total_reviews']

    def create(self, validated_data):
        cloudinary_url = validated_data.pop('cloudinary_url', None)
        product = Product.objects.create(**validated_data)
        
        if cloudinary_url:
            ProductImage.objects.create(
                product=product, 
                image=cloudinary_url, # Store full URL string
                is_primary=True
            )
        return product


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_name', 'product_price', 'product_image', 'quantity']

    def get_product_image(self, obj):
        first_image = obj.product.images.filter(is_primary=True).first()
        if first_image:
            # CHANGED: Return as string to avoid domain prepending
            return str(first_image.image)
        return None

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'total_price', 'created_at']
        read_only_fields = ['user', 'total_price']

    def get_total_price(self, obj):
        return sum(item.product.price * item.quantity for item in obj.items.all())

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price_at_purchase']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'buyer', 'store', 'items', 'total_price', 
            'delivery_status', 'payment_status', 'shipping_address_json', 'created_at'
        ]
        read_only_fields = ['buyer', 'total_price', 'delivery_status', 'payment_status']