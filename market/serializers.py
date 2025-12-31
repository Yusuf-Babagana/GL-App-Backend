from rest_framework import serializers
from .models import Category, Store, Product, ProductImage, Order, OrderItem, Cart, CartItem

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon']

class StoreSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = Store
        fields = ['id', 'owner', 'owner_name', 'name', 'description', 'logo', 'rating', 'total_sales']
        read_only_fields = ['owner', 'rating', 'total_sales']

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary']

class ProductSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(max_length=1000000, allow_empty_file=False, use_url=False),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'store_name', 'category', 'name', 'description', 
            'price', 'currency', 'stock', 'video', 'images', 'uploaded_images',
            'average_rating', 'total_reviews', 'created_at'
        ]
        read_only_fields = ['store', 'average_rating', 'total_reviews']

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        product = Product.objects.create(**validated_data)
        
        # Handle Image Uploads
        for idx, image in enumerate(uploaded_images):
            ProductImage.objects.create(
                product=product, 
                image=image, 
                is_primary=(idx == 0) # First image is primary
            )
        return product

# --- MISSING SERIALIZERS ADDED BELOW ---

class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_name', 'product_price', 'product_image', 'quantity']

    def get_product_image(self, obj):
        # Return first image if available
        first_image = obj.product.images.filter(is_primary=True).first()
        if first_image:
            return first_image.image.url
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

# --- END ADDED SECTIONS ---

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