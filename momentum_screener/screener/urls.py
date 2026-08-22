from django.urls import path
from . import views

app_name = 'screener'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('community/', views.community_view, name='community'),
    path('community/post/<int:post_id>/', views.community_post_detail, name='community_post_detail'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('guest-trial/', views.guest_trial_view, name='guest_trial'),
    path('api/historical/', views.historical_proxy_view, name='historical_proxy'),
    path('api/generate-campaign/', views.generate_campaign_view, name='generate_campaign'),
    path('api/analyze-stock/', views.analyze_stock_ai_view, name='analyze_stock_ai'),
    path('api/upgrade-premium/', views.upgrade_premium_view, name='upgrade_premium'),
    path('api/forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('api/admin/sync-dump/', views.admin_sync_data_dump, name='admin_sync_data_dump'),
    path('api/admin/list-users/', views.admin_list_users, name='admin_list_users'),
    path('api/admin/downgrade-user/', views.admin_downgrade_user, name='admin_downgrade_user'),
    path('api/admin/upgrade-user/', views.admin_upgrade_user, name='admin_upgrade_user'),
    path('api/admin/notifications/', views.admin_notifications_list, name='admin_notifications_list'),
    path('api/admin/notifications/clear/', views.admin_notifications_clear, name='admin_notifications_clear'),
    path('api/admin/payments/verify/', views.admin_verify_payment_view, name='admin_verify_payment'),
    path('api/admin/payments/pending/', views.admin_pending_payments_list_view, name='admin_pending_payments_list'),
    path('api/admin/run-marketing-agent/', views.admin_run_marketing_agent_view, name='admin_run_marketing_agent'),
    path('api/notifications/clear/', views.clear_user_notifications_view, name='clear_user_notifications'),
    path('api/simulation/dump/', views.simulation_dump_view, name='simulation_dump_view'),
    
    # Journal API routes
    path('api/journal/', views.api_journal_get, name='api_journal_get'),
    path('api/journal/add/', views.api_journal_add, name='api_journal_add'),
    path('api/journal/close/', views.api_journal_close, name='api_journal_close'),
    path('api/journal/delete/', views.api_journal_delete, name='api_journal_delete'),
    path('api/journal/clear/', views.api_journal_clear, name='api_journal_clear'),
]
