from django.utils import timezone
from rest_framework import serializers
from .models import Category, Shop, Product, ProductImage, Order, OrderItem, Cart, CartItem, PromotedPost
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
    cloudinary_url = serializers.URLField(write_only=True, required=False, allow_blank=True)

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
                image=cloudinary_url,
                is_primary=True
            )
        return product

    def update(self, instance, validated_data):
        cloudinary_url = validated_data.pop('cloudinary_url', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if cloudinary_url:
            ProductImage.objects.update_or_create(
                product=instance,
                is_primary=True,
                defaults={'image': cloudinary_url}
            )

        return instance


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


class PromotedPostSerializer(serializers.ModelSerializer):
    """
    Read-only representation, used by the active-ticker/banner list and detail
    endpoints. Denormalizes a single unified shape for both promotion_type values
    (product-linked vs. standalone item) so the client doesn't need to branch.
    """
    user_name = serializers.ReadOnlyField(source='user.full_name')
    product_id = serializers.ReadOnlyField(source='product.id')
    product_name = serializers.ReadOnlyField(source='product.name')
    product_image = serializers.ReadOnlyField(source='product.image')
    title = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    whatsapp_number = serializers.SerializerMethodField()
    time_remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = PromotedPost
        fields = [
            'id', 'user_name', 'text_content', 'promotion_type', 'contact_preference',
            'product_id', 'product_name', 'product_image',
            'title', 'image', 'images', 'price', 'location',
            'seller_name', 'phone_number', 'whatsapp_number',
            'duration_type', 'created_at', 'expires_at', 'time_remaining_seconds',
        ]

    def _is_standalone(self, obj):
        return obj.promotion_type == PromotedPost.PromotionType.STANDALONE and obj.standalone_ad_id

    def get_title(self, obj):
        if self._is_standalone(obj):
            return obj.standalone_ad.title
        return obj.product.name if obj.product else None

    def get_image(self, obj):
        if self._is_standalone(obj):
            images = list(obj.standalone_ad.images.all())
            primary = next((img for img in images if img.is_primary), images[0] if images else None)
            return primary.image if primary else None
        return obj.product.image if obj.product else None

    def get_images(self, obj):
        if self._is_standalone(obj):
            return [img.image for img in obj.standalone_ad.images.all()]
        if obj.product:
            urls = [img.image for img in obj.product.images.all()]
            return urls or ([obj.product.image] if obj.product.image else [])
        return []

    def get_price(self, obj):
        if self._is_standalone(obj):
            return obj.standalone_ad.price
        return obj.product.price if obj.product else None

    def get_location(self, obj):
        return obj.standalone_ad.location if self._is_standalone(obj) else None

    def get_seller_name(self, obj):
        if self._is_standalone(obj):
            return obj.standalone_ad.owner.full_name
        if obj.product and obj.product.shop:
            return obj.product.shop.name
        return obj.user.full_name

    def get_phone_number(self, obj):
        if self._is_standalone(obj):
            return obj.standalone_ad.phone_number
        if obj.product and obj.product.shop:
            return obj.product.shop.business_phone
        return None

    def get_whatsapp_number(self, obj):
        if self._is_standalone(obj):
            return obj.standalone_ad.whatsapp_number or obj.standalone_ad.phone_number
        if obj.product and obj.product.shop:
            return obj.product.shop.business_phone
        return None

    def get_time_remaining_seconds(self, obj):
        if not obj.expires_at:
            return None
        return max(0, int((obj.expires_at - timezone.now()).total_seconds()))


class PromotedPostCreateSerializer(serializers.ModelSerializer):
    """
    Input serializer for creating a promoted post — either for an existing
    Product the user owns, or a standalone item they're selling with no
    marketplace listing. Payment/activation and StandaloneAd creation are
    handled in the view (validated_data is read directly, not .save()'d here).
    """
    promotion_type = serializers.ChoiceField(
        choices=PromotedPost.PromotionType.choices, default=PromotedPost.PromotionType.PRODUCT
    )
    contact_preference = serializers.ChoiceField(
        choices=PromotedPost.ContactPreference.choices, default=PromotedPost.ContactPreference.CHAT
    )
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)

    # Standalone-item fields — only required when promotion_type == 'standalone'.
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    location = serializers.CharField(required=False, allow_blank=True, max_length=255)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    whatsapp_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    images = serializers.ListField(child=serializers.URLField(), required=False, allow_empty=True, default=list)

    class Meta:
        model = PromotedPost
        fields = [
            'text_content', 'promotion_type', 'contact_preference', 'duration_type', 'product',
            'title', 'description', 'price', 'location', 'phone_number', 'whatsapp_number',
            'category', 'images',
        ]

    def validate(self, data):
        request = self.context.get('request')
        promotion_type = data.get('promotion_type', PromotedPost.PromotionType.PRODUCT)

        if promotion_type == PromotedPost.PromotionType.PRODUCT:
            product = data.get('product')
            if not product:
                raise serializers.ValidationError({"product": "Select a product to promote."})
            if not request or product.shop is None or product.shop.owner_id != request.user.id:
                raise serializers.ValidationError({"product": "You can only promote your own products."})
        else:
            if not data.get('title'):
                raise serializers.ValidationError({"title": "Give your item a title."})
            if not data.get('phone_number'):
                raise serializers.ValidationError({"phone_number": "A contact phone number is required."})

        return data