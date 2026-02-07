from rest_framework import serializers
from .models import Category, Store, Product, ProductImage, Order, OrderItem, Cart, CartItem

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon']

class StoreSerializer(serializers.ModelSerializer):
    # Dynamic field to show how many products the store has
    product_count = serializers.SerializerMethodField()
    owner_name = serializers.ReadOnlyField(source='owner.full_name')

    class Meta:
        model = Store
        fields = [
            'id', 
            'name', 
            'description', 
            'logo', 
            'is_verified', 
            'owner_name', 
            'product_count',
            'created_at'
        ]

    def get_product_count(self, obj):
        # Accessing the related products through the reverse relation
        return obj.products.count()

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary']

        
class ProductSerializer(serializers.ModelSerializer):
    store = StoreSerializer(read_only=True) 
    images = ProductImageSerializer(many=True, read_only=True)
    

    chat_partner_id = serializers.ReadOnlyField(source='store.owner.id')
    chat_partner_name = serializers.ReadOnlyField(source='store.owner.full_name')
    chat_partner_image = serializers.ImageField(source='store.owner.profile_image', read_only=True)
    
    # NEW FIELDS for Chat Integration
    seller_id = serializers.ReadOnlyField(source='store.owner.id')
    store_name = serializers.ReadOnlyField(source='store.name')

    # Receive URL from mobile app
    cloudinary_url = serializers.URLField(write_only=True, required=False)
    # Allow 'video' to be a string or blank so the 'not a file' error stops
    video = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    video_url = serializers.SerializerMethodField()
    # Add 'image' field for single primary image access
    image = serializers.SerializerMethodField()

    def get_video_url(self, obj):
        if not obj.video:
            return None
        # Return the string directly if it's a URL
        return str(obj.video)

    def get_image(self, obj):
        # 1. Look for actual uploaded images (The /image/upload/ links)
        # Check the related ProductImage model
        first_img = obj.images.first()
        if first_img:
            return str(first_img.image)

        # 2. Fallback to the direct image field if populated
        if hasattr(obj, 'image') and obj.image and str(obj.image).startswith('http'):
            return str(obj.image)

        # 3. Last Resort: Video thumbnail (The /video/upload/ links)
        if obj.video:
            return str(obj.video).replace('/video/upload/', '/video/upload/so_0,f_jpg/')
            
        return None

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'price', 'store', 'image', 'images', 
            'video', 'video_url', 'is_ad', 'stock', 'description', 'category',
            'currency', 'cloudinary_url', 'chat_partner_id', 'chat_partner_name', 
            'chat_partner_image', 'created_at', 'seller_id', 'store_name'
        ]
        read_only_fields = ['store', 'average_rating', 'total_reviews']

    def to_internal_value(self, data):
        # Handle empty strings from FormData
        if 'stock' in data and data['stock'] == '':
            data['stock'] = 1 # Default to 1
        
        if 'category' in data and data['category'] == '':
            data['category'] = None # Allow null category

        return super().to_internal_value(data)

    def create(self, validated_data):
        cloudinary_url = validated_data.pop('cloudinary_url', None)
        # Ensure video_url is saved to the video field
        video_url = validated_data.pop('video', None) 
        
        product = Product.objects.create(**validated_data)
        
        if video_url:
            product.video = video_url # Save the URL string to the FileField (it works safely as Char)
            product.save()
        
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
    # Add this to ensure the frontend can see the price
    price = serializers.DecimalField(source='price_at_purchase', max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'price_at_purchase']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    # Add Store details so the "Track Rider" map knows the store name
    store_name = serializers.ReadOnlyField(source='store.name')
    # Add these two lines for the Buyer to contact the Rider
    rider_name = serializers.ReadOnlyField(source='rider.full_name')
    rider_phone = serializers.ReadOnlyField(source='rider.phone_number') # Ensure this field exists in your User model
    
    class Meta:
        model = Order
        fields = [
            'id', 'buyer', 'store', 'store_name', 'items', 'total_price', 
            'delivery_status', 'payment_status', 'delivery_code', 
            'shipping_address_json', 'rider_name', 'rider_phone', 'created_at'
        ]
        # REMOVE 'delivery_status' from read_only so the Seller can update it!
        read_only_fields = ['buyer', 'total_price', 'payment_status']