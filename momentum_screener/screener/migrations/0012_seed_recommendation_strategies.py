# Generated manually to seed baseline recommendation strategies
from django.db import migrations
import json

def seed_strategies(apps, schema_editor):
    RecommendationStrategy = apps.get_model('screener', 'RecommendationStrategy')
    default_strategies = [
        {
            'name': 'Optimized 45/195 Golden Crossover',
            'slug': 'golden-crossover-45-195',
            'category': 'golden_cross',
            'description': 'Optimized swing trading framework using 45-day and 195-day Simple Moving Averages tailored for Indian high-beta equities with volume breakout validation.',
            'parameters_json': json.dumps({'fast_ma': 45, 'slow_ma': 195, 'ma_type': 'SMA', 'volume_multiple': 1.25, 'rsi_min': 45}),
            'win_rate': 0.0,
            'total_signals': 0,
            'avg_return_pct': 0.0,
            'is_active': True,
        },
        {
            'name': 'RSI Dynamic Momentum Breakout',
            'slug': 'rsi-momentum-breakout',
            'category': 'rsi_breakout',
            'description': 'Momentum surge strategy triggering on 14-day RSI breaking above 62 with 1.5x average 20-day institutional volume expansion.',
            'parameters_json': json.dumps({'rsi_length': 14, 'rsi_threshold': 62, 'volume_multiple': 1.5, 'lookback_days': 20}),
            'win_rate': 0.0,
            'total_signals': 0,
            'avg_return_pct': 0.0,
            'is_active': True,
        },
        {
            'name': 'MACD Velocity Shift (8/21/5)',
            'slug': 'macd-velocity-shift',
            'category': 'macd_cross',
            'description': 'Fast-reactive MACD momentum crossover system capturing early trend acceleration above the 200 SMA structural support.',
            'parameters_json': json.dumps({'fast_period': 8, 'slow_period': 21, 'signal_period': 5, 'confirm_above_200_sma': True}),
            'win_rate': 0.0,
            'total_signals': 0,
            'avg_return_pct': 0.0,
            'is_active': True,
        },
        {
            'name': 'Volatility Squeeze & Expansion',
            'slug': 'volatility-squeeze-breakout',
            'category': 'volatility_squeeze',
            'description': 'Identifies multi-week low volatility compression followed by directional volatility expansion and trend impulse.',
            'parameters_json': json.dumps({'bollinger_period': 20, 'keltner_period': 20, 'squeeze_threshold': 1.0, 'atr_stop_multiplier': 1.8}),
            'win_rate': 0.0,
            'total_signals': 0,
            'avg_return_pct': 0.0,
            'is_active': True,
        },
        {
            'name': 'Trend Pullback & Key Level Re-Test',
            'slug': 'trend-pullback-retest',
            'category': 'pullback',
            'description': 'Buys shallow corrective pullbacks to rising 50 EMA / 200 SMA key support levels within confirmed higher timeframe uptrends.',
            'parameters_json': json.dumps({'trend_ema': 50, 'pullback_pct': 2.5, 'support_level': 'EMA50_OR_SMA200'}),
            'win_rate': 0.0,
            'total_signals': 0,
            'avg_return_pct': 0.0,
            'is_active': True,
        },
    ]
    for s in default_strategies:
        if not RecommendationStrategy.objects.filter(slug=s['slug']).exists():
            RecommendationStrategy.objects.create(**s)

def unseed_strategies(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('screener', '0011_recommendationstrategy_traderecommendation_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_strategies, unseed_strategies),
    ]
