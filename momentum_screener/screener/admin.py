from django.contrib import admin
from django.utils.html import format_html
from .models import UserProfile, TradeJournal, CommunityPost, StockFundamental, PaymentVerificationRequest

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('get_username', 'get_email', 'referred_by_post', 'trial_started_at', 'total_allowed_days', 'days_remaining', 'is_active', 'is_premium')
    search_fields = ('user__username', 'user__email')
    list_filter = ('is_premium', 'referred_by_post')

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
    list_display = ('title', 'stock_symbol', 'theme', 'total_votes', 'referred_signups', 'created_at')
    search_fields = ('title', 'stock_symbol', 'theme')
    list_filter = ('theme', 'created_at')

    def total_votes(self, obj):
        return obj.q1_bullish + obj.q1_bearish + obj.q1_wait
    total_votes.short_description = 'Poll Submissions'

    def referred_signups(self, obj):
        return obj.referred_profiles.count()
    referred_signups.short_description = 'Referred Signups'


@admin.register(PaymentVerificationRequest)
class PaymentVerificationRequestAdmin(admin.ModelAdmin):
    list_display = ('utr', 'user', 'plan', 'amount', 'upi_id', 'status', 'created_at')
    search_fields = ('utr', 'user__username', 'upi_id')
    list_filter = ('status', 'plan', 'created_at')


@admin.register(StockFundamental)
class StockFundamentalAdmin(admin.ModelAdmin):
    list_display = (
        'ticker', 
        'company_name', 
        'sector', 
        'industry', 
        'colored_magic_score', 
        'piotroski_score', 
        'formatted_roce', 
        'formatted_debt_equity', 
        'formatted_net_margin', 
        'formatted_peg', 
        'formatted_market_cap',
        'peg_is_fallback', 
        'last_updated'
    )
    search_fields = ('ticker', 'company_name', 'sector', 'industry')
    list_filter = ('sector', 'industry', 'peg_is_fallback')
    ordering = ('-magic_score', 'ticker')
    readonly_fields = ('last_updated',)
    list_per_page = 25

    fieldsets = (
        ('Company & Sector Classification', {
            'fields': (
                ('ticker', 'company_name'),
                ('sector', 'industry'),
            )
        }),
        ('Magic Score & Composite Ratios', {
            'fields': (
                ('magic_score', 'piotroski_score'),
                ('roce_pct', 'debt_equity'),
                ('net_margin_pct', 'peg_ratio'),
            )
        }),
        ('PEG Valuation & Fallback Assumptions', {
            'fields': (
                'peg_is_fallback',
                'peg_note',
            )
        }),
        ('Financial Volume & Margins (INR Crores)', {
            'fields': (
                ('market_cap_cr', 'interest_coverage'),
                ('net_profit_cr', 'ebit_cr'),
            )
        }),
        ('Historical Trends & JSON Metadata', {
            'classes': ('collapse',),
            'fields': (
                'score_breakdown_json',
                'yearly_trends_json',
                'last_updated',
            )
        }),
    )

    def colored_magic_score(self, obj):
        score = obj.magic_score
        if score >= 80:
            color = "#10b981"  # Emerald Green
            bg = "rgba(16, 185, 129, 0.15)"
        elif score >= 65:
            color = "#3b82f6"  # Blue
            bg = "rgba(59, 130, 246, 0.15)"
        elif score >= 50:
            color = "#f59e0b"  # Amber
            bg = "rgba(245, 158, 11, 0.15)"
        else:
            color = "#ef4444"  # Red
            bg = "rgba(239, 68, 68, 0.15)"
        return format_html(
            '<span style="display:inline-block; font-weight:700; color:{}; background:{}; padding:2px 8px; border-radius:4px; border:1px solid {}; font-size:12px;">{}</span>',
            color, bg, color, score
        )
    colored_magic_score.short_description = 'Magic Score'
    colored_magic_score.admin_order_field = 'magic_score'

    def formatted_roce(self, obj):
        if obj.roce_pct is not None:
            return f"{obj.roce_pct:.2f}%"
        return "-"
    formatted_roce.short_description = 'ROCE (%)'
    formatted_roce.admin_order_field = 'roce_pct'

    def formatted_debt_equity(self, obj):
        if obj.debt_equity is not None:
            return f"{obj.debt_equity:.2f}"
        return "-"
    formatted_debt_equity.short_description = 'Debt / Eq'
    formatted_debt_equity.admin_order_field = 'debt_equity'

    def formatted_net_margin(self, obj):
        if obj.net_margin_pct is not None:
            return f"{obj.net_margin_pct:.2f}%"
        return "-"
    formatted_net_margin.short_description = 'Net Margin (%)'
    formatted_net_margin.admin_order_field = 'net_margin_pct'

    def formatted_peg(self, obj):
        if obj.peg_ratio is not None:
            suffix = " *" if obj.peg_is_fallback else ""
            return f"{obj.peg_ratio:.2f}{suffix}"
        return "-"
    formatted_peg.short_description = 'PEG'
    formatted_peg.admin_order_field = 'peg_ratio'

    def formatted_market_cap(self, obj):
        if obj.market_cap_cr is not None:
            return f"Rs. {obj.market_cap_cr:,.0f} Cr"
        return "-"
    formatted_market_cap.short_description = 'Mkt Cap'
    formatted_market_cap.admin_order_field = 'market_cap_cr'

