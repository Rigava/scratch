from django.urls import path
from . import views

app_name = 'screener'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('guest-trial/', views.guest_trial_view, name='guest_trial'),
    path('api/historical/', views.historical_proxy_view, name='historical_proxy'),
    path('api/generate-campaign/', views.generate_campaign_view, name='generate_campaign'),
    
    # Journal API routes
    path('api/journal/', views.api_journal_get, name='api_journal_get'),
    path('api/journal/add/', views.api_journal_add, name='api_journal_add'),
    path('api/journal/close/', views.api_journal_close, name='api_journal_close'),
    path('api/journal/delete/', views.api_journal_delete, name='api_journal_delete'),
    path('api/journal/clear/', views.api_journal_clear, name='api_journal_clear'),
]
