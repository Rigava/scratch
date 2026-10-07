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
        'colored_macd_signal',
        'macd_crossover_date',
        'colored_rsi_signal',
        'rsi_crossover_date',
        'piotroski_score', 
        'formatted_roce', 
        'formatted_debt_equity', 
        'formatted_net_margin', 
        'formatted_peg', 
        'formatted_market_cap',
        'peg_is_fallback', 
        'last_updated'
    )
    search_fields = ('ticker', 'company_name', 'sector', 'industry', 'macd_signal', 'rsi_signal')
    list_filter = ('sector', 'industry', 'macd_signal', 'rsi_signal', 'peg_is_fallback')
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
        ('Technical Momentum & Crossovers', {
            'fields': (
                ('macd_signal', 'macd_crossover_date'),
                ('rsi_signal', 'rsi_crossover_date'),
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

    def colored_macd_signal(self, obj):
        sig = obj.macd_signal or "Neutral"
        if "Bullish" in sig:
            color = "#10b981"
            bg = "rgba(16, 185, 129, 0.15)"
        elif "Bearish" in sig:
            color = "#ef4444"
            bg = "rgba(239, 68, 68, 0.15)"
        else:
            color = "#64748b"
            bg = "rgba(100, 116, 139, 0.15)"
        return format_html(
            '<span style="display:inline-block; font-weight:600; color:{}; background:{}; padding:2px 7px; border-radius:4px; font-size:11px; white-space:nowrap;">{}</span>',
            color, bg, sig
        )
    colored_macd_signal.short_description = 'MACD Signal'
    colored_macd_signal.admin_order_field = 'macd_signal'

    def colored_rsi_signal(self, obj):
        sig = obj.rsi_signal or "Neutral"
        if "Bullish" in sig:
            color = "#10b981"
            bg = "rgba(16, 185, 129, 0.15)"
        elif "Bearish" in sig:
            color = "#ef4444"
            bg = "rgba(239, 68, 68, 0.15)"
        else:
            color = "#64748b"
            bg = "rgba(100, 116, 139, 0.15)"
        return format_html(
            '<span style="display:inline-block; font-weight:600; color:{}; background:{}; padding:2px 7px; border-radius:4px; font-size:11px; white-space:nowrap;">{}</span>',
            color, bg, sig
        )
    colored_rsi_signal.short_description = 'RSI Signal'
    colored_rsi_signal.admin_order_field = 'rsi_signal'

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


from .models import RecommendationStrategy, TradeRecommendation, TradeUpdateLog

@admin.register(RecommendationStrategy)
class RecommendationStrategyAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'get_fast_slow_ma', 'total_signals', 'win_rate_display', 'is_active', 'updated_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}

    def get_fast_slow_ma(self, obj):
        p = obj.parameters
        if 'fast_ma' in p and 'slow_ma' in p:
            return f"{p.get('fast_ma')}/{p.get('slow_ma')} {p.get('ma_type', 'SMA')}"
        elif 'rsi_threshold' in p:
            return f"RSI > {p.get('rsi_threshold')}"
        elif 'fast_period' in p:
            return f"MACD {p.get('fast_period')}/{p.get('slow_period')}/{p.get('signal_period')}"
        return "-"
    get_fast_slow_ma.short_description = 'Parameters'

    def win_rate_display(self, obj):
        color = '#10b981' if (obj.win_rate or 0) >= 60 else '#f59e0b'
        val = f"{obj.win_rate or 0:.1f}%"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, val)
    win_rate_display.short_description = 'Win Rate'


@admin.register(TradeRecommendation)
class TradeRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        'ticker',
        'strategy',
        'direction_badge',
        'colored_status',
        'entry_range',
        'target_1',
        'stop_loss',
        'trailing_stop_loss',
        'outcome_display',
        'holding_days',
        'initiated_at',
        'created_at'
    )
    list_filter = ('status', 'strategy', 'direction', 'is_winning_trade', 'created_at')
    search_fields = ('ticker', 'company_name', 'thesis_summary')
    readonly_fields = ('holding_days', 'realized_gain_loss_pct', 'is_winning_trade', 'created_at', 'updated_at')
    actions = ['mark_active', 'mark_target_1_hit', 'mark_completed_profit', 'mark_sl_hit', 'mark_cancelled']

    def direction_badge(self, obj):
        bg = '#10b981' if obj.direction == 'BUY' else '#ef4444'
        return format_html('<span style="background: {}; color: #fff; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>', bg, obj.direction)
    direction_badge.short_description = 'Dir'

    def colored_status(self, obj):
        colors = {
            'draft': ('#64748b', '#f1f5f9'),
            'pending': ('#f59e0b', '#fffbeb'),
            'active': ('#3b82f6', '#eff6ff'),
            'target_1_hit': ('#06b6d4', '#ecfeff'),
            'target_2_hit': ('#8b5cf6', '#f5f3ff'),
            'completed_profit': ('#10b981', '#f0fdf4'),
            'sl_hit': ('#ef4444', '#fef2f2'),
            'cancelled': ('#94a3b8', '#f8fafc'),
        }
        bg, text_color = colors.get(obj.status, ('#64748b', '#ffffff'))
        return format_html('<span style="background: {}; color: #fff; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px;">{}</span>', bg, obj.get_status_display())
    colored_status.short_description = 'Status'

    def entry_range(self, obj):
        return f"Rs. {obj.entry_price_min} - {obj.entry_price_max}"
    entry_range.short_description = 'Entry Range'

    def outcome_display(self, obj):
        if obj.realized_gain_loss_pct is not None:
            color = '#10b981' if obj.realized_gain_loss_pct > 0 else '#ef4444'
            prefix = '+' if obj.realized_gain_loss_pct > 0 else ''
            val = f"{prefix}{obj.realized_gain_loss_pct:.2f}%"
            return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, val)
        return "-"
    outcome_display.short_description = 'Realized P&L'

    # Admin actions
    def mark_active(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        updated = queryset.update(status='active', initiated_at=now)
        for obj in queryset:
            TradeUpdateLog.objects.create(recommendation=obj, old_status='pending', new_status='active', notes='Marked active via admin bulk action')
        self.message_user(request, f"{updated} recommendations marked as ACTIVE.")
    mark_active.short_description = "Status -> Active (Triggered)"

    def mark_target_1_hit(self, request, queryset):
        for obj in queryset:
            old = obj.status
            obj.status = 'target_1_hit'
            obj.trailing_stop_loss = obj.entry_price_min
            obj.save()
            TradeUpdateLog.objects.create(recommendation=obj, old_status=old, new_status='target_1_hit', trigger_price=obj.target_1, notes='Target 1 Hit. Trailing SL moved to entry.')
        self.message_user(request, f"{queryset.count()} recommendations updated to TARGET 1 HIT.")
    mark_target_1_hit.short_description = "Status -> Target 1 Hit (Trail SL to Cost)"

    def mark_completed_profit(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        for obj in queryset:
            old = obj.status
            obj.status = 'completed_profit'
            obj.closed_at = now
            obj.is_winning_trade = True
            if obj.target_2:
                obj.exit_price = obj.target_2
            elif obj.target_1:
                obj.exit_price = obj.target_1
            if obj.entry_price_min and obj.exit_price:
                gain_pct = ((float(obj.exit_price) - float(obj.entry_price_min)) / float(obj.entry_price_min)) * 100
                obj.realized_gain_loss_pct = round(gain_pct, 2)
            if obj.initiated_at:
                obj.holding_days = max(1, (now - obj.initiated_at).days)
            obj.save()
            TradeUpdateLog.objects.create(recommendation=obj, old_status=old, new_status='completed_profit', trigger_price=obj.exit_price, notes='Trade marked closed in profit.')
        self.message_user(request, f"{queryset.count()} recommendations marked as COMPLETED (PROFIT).")
    mark_completed_profit.short_description = "Status -> Completed (Profit Booked)"

    def mark_sl_hit(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        for obj in queryset:
            old = obj.status
            obj.status = 'sl_hit'
            obj.closed_at = now
            obj.is_winning_trade = False
            effective_sl = obj.trailing_stop_loss or obj.stop_loss
            obj.exit_price = effective_sl
            if obj.entry_price_min and effective_sl:
                loss_pct = ((float(effective_sl) - float(obj.entry_price_min)) / float(obj.entry_price_min)) * 100
                obj.realized_gain_loss_pct = round(loss_pct, 2)
                obj.is_winning_trade = loss_pct > 0  # If trailing SL was above entry
            if obj.initiated_at:
                obj.holding_days = max(1, (now - obj.initiated_at).days)
            obj.save()
            TradeUpdateLog.objects.create(recommendation=obj, old_status=old, new_status='sl_hit', trigger_price=effective_sl, notes='Stop Loss Triggered.')
        self.message_user(request, f"{queryset.count()} recommendations marked as STOP LOSS HIT.")
    mark_sl_hit.short_description = "Status -> Stop Loss Triggered (Closed)"

    def mark_cancelled(self, request, queryset):
        for obj in queryset:
            old = obj.status
            obj.status = 'cancelled'
            obj.save()
            TradeUpdateLog.objects.create(recommendation=obj, old_status=old, new_status='cancelled', notes='Trade cancelled / setup invalidated prior to entry.')
        self.message_user(request, f"{queryset.count()} recommendations marked as CANCELLED.")
    mark_cancelled.short_description = "Status -> Cancelled (Invalidated)"


@admin.register(TradeUpdateLog)
class TradeUpdateLogAdmin(admin.ModelAdmin):
    list_display = ('recommendation', 'old_status', 'new_status', 'trigger_price', 'created_at', 'notes_snippet')
    list_filter = ('new_status', 'created_at')
    search_fields = ('recommendation__ticker', 'notes')

    def notes_snippet(self, obj):
        return (obj.notes[:60] + '...') if len(obj.notes) > 60 else obj.notes
    notes_snippet.short_description = 'Notes'


