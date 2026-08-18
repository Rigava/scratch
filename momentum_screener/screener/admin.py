from django.contrib import admin
from .models import UserProfile, TradeJournal, CommunityPost

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('get_username', 'get_email', 'trial_started_at', 'total_allowed_days', 'days_remaining', 'is_active', 'is_premium')
    search_fields = ('user__username', 'user__email')
    list_filter = ('is_premium',)

    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'

    def is_active(self, obj):
        return obj.is_trial_active()
    is_active.boolean = True
    is_active.short_description = 'Trial Active?'

@admin.register(TradeJournal)
class TradeJournalAdmin(admin.ModelAdmin):
    list_display = ('user', 'ticker', 'trade_type', 'status', 'entry_date', 'entry_price', 'exit_date', 'exit_price', 'pnl')
    search_fields = ('user__username', 'ticker')
    list_filter = ('status', 'trade_type')


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'stock_symbol', 'theme', 'created_at')
    search_fields = ('title', 'stock_symbol', 'theme')
    list_filter = ('theme', 'created_at')

