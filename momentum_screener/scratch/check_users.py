import os
import sys
import django

sys.path.insert(0, '')
os.environ['DJANGO_SETTINGS_MODULE'] = 'momentum_screener.settings'
django.setup()

from django.contrib.auth.models import User
from screener.models import UserProfile

print("=== USER LIST ===")
for u in User.objects.all():
    profile = getattr(u, 'profile', None)
    plan_tier = profile.plan_tier if profile else "No Profile"
    is_premium = profile.is_premium if profile else False
    print(f"Username: {u.username}")
    print(f"  is_staff: {u.is_staff}")
    print(f"  is_superuser: {u.is_superuser}")
    print(f"  plan_tier: {plan_tier}")
    print(f"  is_premium: {is_premium}")
    print("-" * 30)
