from django.urls import path
from . import views

app_name = 'screener'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('api/historical/', views.historical_proxy_view, name='historical_proxy'),
    path('api/generate-campaign/', views.generate_campaign_view, name='generate_campaign'),
]
