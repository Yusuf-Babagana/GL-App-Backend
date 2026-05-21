from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ('sender', 'recipient', 'text', 'attachment', 'is_read', 'created_at')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_context', 'created_at', 'updated_at')
    list_filter = ('created_at',)
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'recipient', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('text', 'sender__email', 'recipient__email')
    readonly_fields = ('created_at',)

