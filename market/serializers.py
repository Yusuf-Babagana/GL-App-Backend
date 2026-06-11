from rest_framework import serializers
from .models import Category, Shop, Product, ProductImage, Order, OrderItem, Cart, CartItem
from users.serializers import UserSerializer

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon']

class ShopSerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()
    owner_name = serializers.ReadOnlyField(source='owner.full_name')
    owner_id = serializers.ReadOnlyField(source='owner.id')

    class Meta:
        model = Shop
        fields = [
            'id', 
            'name', 
            'description', 
            'logo', 
            'is_active', 
            'owner_id',
            'owner_name', 
            'product_count',
            'created_at',
            'rejection_reason'
        ]

    def get_product_count(self, obj):
        return obj.products.count()

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary']

        
class ProductSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True) 
    images = ProductImageSerializer(many=True, read_only=True)
    

    chat_partner_id = serializers.ReadOnlyField(source='shop.owner.id')
    chat_partner_name = serializers.ReadOnlyField(source='shop.owner.full_name')
    chat_partner_image = serializers.ImageField(source='shop.owner.profile_image', read_only=True)
    
    # NEW FIELDS for Chat Integration
    seller_id = serializers.ReadOnlyField(source='shop.owner.id')
    shop_name = serializers.ReadOnlyField(source='shop.name')

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True
    )
    image = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    video_url = serializers.URLField(
        required=False, allow_blank=True, allow_null=True, source='video'
    )

    # Receive URL from mobile app
    cloudinary_url = serializers.URLField(write_only=True, required=False)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'price', 'shop', 'image', 'images', 
            'video_ad_url', 'video_url', 'is_ad', 'stock', 'description', 'category',
            'currency', 'cloudinary_url', 'chat_partner_id', 'chat_partner_name', 
            'chat_partner_image', 'created_at', 'seller_id', 'shop_name'
        ]
        read_only_fields = [
            'shop', 'average_rating', 'total_reviews', 'created_at',
            'chat_partner_id', 'chat_partner_name', 'chat_partner_image',
            'seller_id', 'shop_name', 'video_ad_url',
        ]

    def validate(self, data):
        return data

    def to_internal_value(self, data):
        if 'stock' in data and data['stock'] == '':
            data['stock'] = 1
        if 'category' in data and data['category'] == '':
            data['category'] = None
        return super().to_internal_value(data)

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

class CartSyncInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=0)


class CartSyncItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    name = serializers.CharField(source='product.name', read_only=True)
    price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    image = serializers.SerializerMethodField()
    stock_available = serializers.IntegerField(source='product.stock', read_only=True)
    stock_warning = serializers.SerializerMethodField()
    synced_quantity = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    def get_image(self, obj):
        product = obj.get('product') if isinstance(obj, dict) else obj.product
        first_image = product.images.filter(is_primary=True).first()
        return str(first_image.image) if first_image else None

    def get_stock_warning(self, obj):
        requested = obj.get('quantity', 0) if isinstance(obj, dict) else obj.quantity
        product = obj.get('product') if isinstance(obj, dict) else obj.product
        available = product.stock
        if available == 0:
            return "Out of stock"
        if requested > available:
            return f"Only {available} item(s) available"
        return None


class CartSyncResponseSerializer(serializers.Serializer):
    synced_items = CartSyncItemSerializer(many=True)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    synced_at = serializers.DateTimeField()


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    price = serializers.DecimalField(source='price_at_purchase', max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'price_at_purchase']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    buyer = UserSerializer(read_only=True)
    shop_name = serializers.ReadOnlyField(source='shop.name')
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer', 'shop', 'shop_name', 'items', 'total_price', 
            'delivery_status', 'payment_status', 
            'shipping_address_json', 'created_at'
        ]
        read_only_fields = ['order_number', 'buyer', 'total_price', 'payment_status']


class BuyerOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shop_name = serializers.ReadOnlyField(source='shop.name')
    shop_logo = serializers.ReadOnlyField(source='shop.logo')
    seller_phone = serializers.SerializerMethodField()

    def get_seller_phone(self, obj):
        try:
            if obj.shop and obj.shop.owner:
                return obj.shop.owner.phone_number
        except Exception:
            pass
        return None

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'shop', 'shop_name', 'shop_logo', 'items', 'total_price',
            'delivery_status', 'payment_status',
            'shipping_address_json', 'seller_phone', 'created_at'
        ]
        read_only_fields = fields


class SellerOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    buyer_name = serializers.ReadOnlyField(source='buyer.full_name')
    buyer_phone = serializers.ReadOnlyField(source='buyer.phone_number')
    buyer_email = serializers.ReadOnlyField(source='buyer.email')

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer_name', 'buyer_phone', 'buyer_email',
            'items', 'total_price',
            'delivery_status', 'payment_status',
            'shipping_address_json', 'created_at'
        ]
        read_only_fields = ['order_number', 'buyer_name', 'buyer_phone', 'buyer_email',
                           'total_price', 'payment_status', 'created_at']


class CheckoutItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

class CheckoutInputSerializer(serializers.Serializer):
    items = CheckoutItemSerializer(many=True, required=False)
    payment_method = serializers.ChoiceField(
        choices=['wallet'], required=False, default=None
    )
    shipping_address = serializers.JSONField(required=False)

class BuyNowInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(default=1, min_value=1)
    payment_method = serializers.ChoiceField(
        choices=['wallet'], required=False, default=None
    )
    shipping_address = serializers.JSONField(required=False)