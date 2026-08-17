from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

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

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def total_allowed_days(self):
        return self.trial_duration_days + self.extended_duration_days

    def is_trial_active(self):
        if self.is_premium or self.plan_tier in ['classic', 'pro']:
            return True
        expiry = self.trial_started_at + datetime.timedelta(days=self.total_allowed_days)
        return timezone.now() < expiry

    def days_remaining(self):
        if self.is_premium or self.plan_tier in ['classic', 'pro']:
            return 9999
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

