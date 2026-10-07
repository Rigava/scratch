from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime
import json

class UserProfile(models.Model):
    PLAN_TIERS = (
        ('standard', 'Standard (Free)'),
        ('classic', 'Classic (₹299 One-time)'),
        ('pro', 'Pro Analyst (₹199/Month)'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    trial_started_at = models.DateTimeField(default=timezone.now)
    trial_duration_days = models.IntegerField(default=7)
    extended_duration_days = models.IntegerField(default=0)
    is_premium = models.BooleanField(default=False)
    plan_tier = models.CharField(max_length=15, choices=PLAN_TIERS, default='standard')
    has_used_trial = models.BooleanField(default=False)
    pro_expires_at = models.DateTimeField(null=True, blank=True)
    referred_by_post = models.ForeignKey('CommunityPost', null=True, blank=True, on_delete=models.SET_NULL, related_name='referred_profiles')

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def total_allowed_days(self):
        return self.trial_duration_days + self.extended_duration_days

    def is_trial_active(self):
        if self.is_premium or self.plan_tier == 'classic':
            return True
        if self.plan_tier == 'pro':
            if self.pro_expires_at:
                return timezone.now() < self.pro_expires_at
            return False
        expiry = self.trial_started_at + datetime.timedelta(days=self.total_allowed_days)
        return timezone.now() < expiry

    def days_remaining(self):
        if self.is_premium or self.plan_tier == 'classic':
            return 9999
        if self.plan_tier == 'pro':
            if not self.pro_expires_at:
                return 0
            delta = self.pro_expires_at - timezone.now()
            total_seconds = delta.total_seconds()
            if total_seconds <= 0:
                return 0
            import math
            return math.ceil(total_seconds / 86400)
        expiry = self.trial_started_at + datetime.timedelta(days=self.total_allowed_days)
        delta = expiry - timezone.now()
        total_seconds = delta.total_seconds()
        if total_seconds <= 0:
            return 0
        import math
        return math.ceil(total_seconds / 86400)

class TradeJournal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trades')
    ticker = models.CharField(max_length=20)
    trade_type = models.CharField(max_length=10) # Long, Short
    entry_date = models.CharField(max_length=15) # YYYY-MM-DD
    entry_price = models.FloatField()
    quantity = models.IntegerField(default=10)
    stop_loss = models.FloatField(null=True, blank=True)
    entry_reason = models.TextField(blank=True, default='')
    exit_date = models.CharField(max_length=15, null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    exit_reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=15, default='Active') # Active, Realized
    pnl = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.ticker} ({self.status})"


class AdminNotification(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class PaymentVerificationRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    plan = models.CharField(max_length=15)
    amount = models.FloatField()
    utr = models.CharField(max_length=20, unique=True)
    upi_id = models.CharField(max_length=50)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment UTR {self.utr} - {self.user.username} ({self.status})"


class UserNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification to {self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class CommunityPost(models.Model):
    title = models.CharField(max_length=200)
    stock_symbol = models.CharField(max_length=20)
    theme = models.CharField(max_length=50)
    theme_display = models.TextField(blank=True, default='')
    twitter_thread_json = models.TextField(default='[]') # JSON stringified array
    linkedin_post = models.TextField(blank=True, default='')
    telegram_digest = models.TextField(blank=True, default='')
    youtube_shorts_script_json = models.TextField(default='{}') # JSON stringified object
    
    # 3-Question Mindset Poll
    question_1 = models.CharField(max_length=250, blank=True, default='')
    question_2 = models.CharField(max_length=250, blank=True, default='')
    question_3 = models.CharField(max_length=250, blank=True, default='')
    
    q1_bullish = models.IntegerField(default=0)
    q1_bearish = models.IntegerField(default=0)
    q1_wait = models.IntegerField(default=0)

    q2_bullish = models.IntegerField(default=0)
    q2_bearish = models.IntegerField(default=0)
    q2_wait = models.IntegerField(default=0)

    q3_bullish = models.IntegerField(default=0)
    q3_bearish = models.IntegerField(default=0)
    q3_wait = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.stock_symbol})"


class StockFundamental(models.Model):
    ticker = models.CharField(max_length=25, unique=True, db_index=True)
    company_name = models.CharField(max_length=150, blank=True, default='')
    market_cap_cr = models.FloatField(null=True, blank=True)
    magic_score = models.IntegerField(default=0, db_index=True)
    piotroski_score = models.IntegerField(default=0)
    peg_ratio = models.FloatField(null=True, blank=True)
    roce_pct = models.FloatField(null=True, blank=True)
    debt_equity = models.FloatField(null=True, blank=True)
    ebit_cr = models.FloatField(null=True, blank=True)
    net_profit_cr = models.FloatField(null=True, blank=True)
    interest_coverage = models.FloatField(null=True, blank=True)
    net_margin_pct = models.FloatField(null=True, blank=True)
    sector = models.CharField(max_length=60, default='', blank=True, db_index=True)
    industry = models.CharField(max_length=80, default='', blank=True, db_index=True)
    peg_is_fallback = models.BooleanField(default=False)
    peg_note = models.CharField(max_length=300, blank=True, default='')
    score_breakdown_json = models.TextField(default='{}')
    yearly_trends_json = models.TextField(default='[]')
    
    # Technical Momentum & Crossover Signals
    macd_signal = models.CharField(max_length=30, blank=True, default='Neutral', db_index=True)
    macd_crossover_date = models.CharField(max_length=15, blank=True, default='')
    rsi_signal = models.CharField(max_length=30, blank=True, default='Neutral', db_index=True)
    rsi_crossover_date = models.CharField(max_length=15, blank=True, default='')

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock Fundamental"
        verbose_name_plural = "Stock Fundamentals"
        ordering = ['-magic_score', 'ticker']

    def __str__(self):
        return f"{self.ticker} (Magic Score: {self.magic_score})"


class RecommendationStrategy(models.Model):
    CATEGORY_CHOICES = [
        ('golden_cross', 'Moving Average Crossover'),
        ('rsi_breakout', 'RSI Momentum Breakout'),
        ('macd_cross', 'MACD Velocity Crossover'),
        ('volatility_squeeze', 'Volatility Squeeze Breakout'),
        ('pullback', 'Trend Pullback & Re-test'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='golden_cross')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    parameters_json = models.TextField(default='{}', help_text="e.g. {'fast_ma': 45, 'slow_ma': 195, 'ma_type': 'SMA'}")

    @property
    def parameters(self):
        try:
            return json.loads(self.parameters_json or '{}')
        except Exception:
            return {}

    @parameters.setter
    def parameters(self, val):
        if isinstance(val, dict):
            self.parameters_json = json.dumps(val)
        else:
            self.parameters_json = str(val)

    total_signals = models.IntegerField(default=0)
    win_rate = models.FloatField(default=0.0)
    avg_return_pct = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Recommendation Strategy"
        verbose_name_plural = "Recommendation Strategies"
        ordering = ['-is_active', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class TradeRecommendation(models.Model):
    DIRECTION_CHOICES = [('BUY', 'Buy / Long'), ('SELL', 'Sell / Short')]
    STATUS_CHOICES = [
        ('draft', 'Draft (Review Pending)'),
        ('pending', 'Pending Entry (Wait for Entry Range)'),
        ('active', 'Active (In Progress)'),
        ('target_1_hit', 'Target 1 Reached (Partial Profit Booked)'),
        ('target_2_hit', 'Target 2 Reached (Holding Runners)'),
        ('completed_profit', 'Closed in Profit'),
        ('sl_hit', 'Stop Loss Hit (Closed)'),
        ('cancelled', 'Cancelled / Invalidated'),
    ]

    ticker = models.CharField(max_length=25, db_index=True)
    company_name = models.CharField(max_length=150, blank=True, default='')
    strategy = models.ForeignKey(RecommendationStrategy, on_delete=models.CASCADE, related_name='recommendations')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='BUY')

    # Price Milestones & Risk Management
    entry_price_min = models.DecimalField(max_digits=10, decimal_places=2)
    entry_price_max = models.DecimalField(max_digits=10, decimal_places=2)
    entry_price_triggered = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    target_1 = models.DecimalField(max_digits=10, decimal_places=2)
    target_2 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    target_3 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    stop_loss = models.DecimalField(max_digits=10, decimal_places=2)
    trailing_stop_loss = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Risk/Reward & Capital Allocation Rules
    risk_reward_ratio = models.CharField(max_length=20, default="1:2.5")
    recommended_allocation_pct = models.FloatField(default=5.0)
    max_risk_pct = models.FloatField(default=1.5)

    # Lifecycle & Timestamps
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='draft', db_index=True)
    initiated_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    holding_days = models.IntegerField(default=0)

    # Financial Outcome Tracking (Accuracy Ledger)
    exit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    realized_gain_loss_pct = models.FloatField(null=True, blank=True)
    is_winning_trade = models.BooleanField(null=True, blank=True)

    # Content & Media
    thesis_summary = models.TextField(blank=True, default='')
    chart_image = models.ImageField(upload_to='trade_charts/%Y/%m/', null=True, blank=True)
    ai_conviction_score = models.IntegerField(default=85)
    strategy_audit_json = models.TextField(blank=True, default='{}')

    @property
    def strategy_audit(self):
        try:
            data = json.loads(self.strategy_audit_json or '{}')
            if data and data.get('criteria_checks'):
                return data
        except Exception:
            pass
        try:
            from .strategy_service import evaluate_strategy_compliance
            return evaluate_strategy_compliance(self.ticker, self.strategy)
        except Exception:
            return {}

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Trade Recommendation"
        verbose_name_plural = "Trade Recommendations"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.direction} {self.ticker} [{self.get_status_display()}]"

    @property
    def is_open(self):
        return self.status in ['pending', 'active', 'target_1_hit', 'target_2_hit']


class TradeUpdateLog(models.Model):
    recommendation = models.ForeignKey(TradeRecommendation, on_delete=models.CASCADE, related_name='update_logs')
    old_status = models.CharField(max_length=25, blank=True, default='')
    new_status = models.CharField(max_length=25)
    trigger_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Trade Update Log"
        verbose_name_plural = "Trade Update Logs"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recommendation.ticker}: {self.old_status} -> {self.new_status}"



