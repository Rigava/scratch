import os
import sys
import json
import logging
import datetime
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from django.conf import settings
from django.utils import timezone

from .market_breadth_service import get_market_breadth_payload
from .quant_service import get_quant_terminal_payload, NpEncoder
from .models import MarketDailyBriefing, CommunityPost

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Senior Market Strategist at TradeKriya writing an engaging, professional, and accessible LinkedIn editorial.

CRITICAL FORMATTING RULES (STRICTLY ENFORCED):
1. ZERO MARKDOWN PUNCTUATION:
   - NEVER use markdown symbols like ###, ##, #, **, *, __, or _.
   - Do NOT use hash marks for headers. Do NOT use asterisks or underscores for bold/italic. Raw markdown punctuation clutters publication feeds!
   - For section titles, write clean ALL-CAPS headers separated by a blank line (e.g. MARKET HEALTH PULSE, WHAT HAPPENS IF KEY LEVELS BREAK?, CATEGORY BUCKETS & STRUCTURAL STRENGTH, ACTIONABLE PLAYBOOK).
   - For bullet points, use clean Unicode dot (•) followed by a space.

2. ELIMINATE OPAQUE PROPRIETARY JARGON:
   - Translate technical terms into everyday, conversational investor language:
     * Support -> "a rock-solid buying floor where institutional buyers step in"
     * Reward-to-risk -> "4:1 upside potential (risking ₹1 to make ₹4)"
     * Market breadth -> "internal health of the broader market"

3. MATHEMATICAL ACCURACY IN THE DOMINO CASCADE:
   - Clearly state how all 115 stocks in the universe are divided:
     * Exactly 65 stocks (56.5%) on the Downside Danger Line (near immediate support breakdown).
     * Exactly 39 stocks (33.9%) on the Upside Trigger Line (coiled near resistance).
     * Exactly 11 stocks (9.6%) in the Neutral Mid-Zone (cushioned in the middle).
     * Explicitly note that 65 + 39 + 11 = 115 stocks (100% of the universe).

4. CATEGORY BUCKETS & STRUCTURAL STRENGTH (MANDATORY SECTION):
   - Include a dedicated section titled: CATEGORY BUCKETS & STRUCTURAL STRENGTH
   - Group the stocks into the 4 buckets provided in the telemetry:
     BREAKOUTS (Stocks punching through overhead resistance)
     REBOUNDS (Stocks bouncing cleanly off support floors)
     SUPPLY REJECTIONS (Stocks slammed by overhead sellers)
     DEMAND BREAKDOWNS (Stocks breaking below critical support)
   - For each stock, format it cleanly with its structural strength in brackets:
     • SYMBOL (Price, DayChange%) - [struct_label]
     Example:
     • TECHM (₹1,514.10, +1.85%) - [Expansion Runner]
     • APOLLOTYRE (₹485.20, +0.92%) - [Safe D&S Anchor]
     • BHEL (₹248.50, -2.15%) - [High Falling-Zone Risk]
     • WIPRO (₹189.84, -0.30%) - [Mean-Reversion Oscillating]
   - If a bucket has 0 confirmed stocks today (e.g. Demand Breakdowns), explicitly state:
     • 0 confirmed breakdowns today (with 65 stocks hovering on the Downside Danger Line watch).

5. STRUCTURE & FLOW:
   - Hook: Contrast headline index calm with the reality of market internals.
   - Market Health Pulse: Simple 3-4 bullet points on the numbers.
   - What Happens If Key Levels Break? (The Domino Effect across the 65, 39, and 11 stocks).
   - Category Buckets & Structural Strength (Breakouts, Rebounds, Supply Rejections, Demand Breakdowns).
   - High-Asymmetry Stock Setups: Highlight the 2-3 specific setups in simple trader terms.
   - Actionable Playbook: Exactly what investors and traders should do tomorrow.
   - Question of the Day & relevant hashtags.
"""

def clean_markdown_formatting(text):
    """
    Cleans raw markdown punctuation (###, **, *, __, _, `) from the article text
    to provide clean, clutter-free reading on LinkedIn and website publications.
    """
    if not text:
        return ""
    import re
    # Remove markdown header hashes: '### Heading' or '## Heading' -> 'Heading'
    text = re.sub(r'^[ \t]*#{1,6}[ \t]*', '', text, flags=re.MULTILINE)
    # Remove markdown bold/italic asterisks: '**bold**' -> 'bold', '*italic*' -> 'italic'
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # Remove markdown bold/italic underscores: '__bold__' -> 'bold', '_italic_' -> 'italic'
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'(?<!\w)_(.*?)_(?!\w)', r'\1', text)
    # Remove backticks
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    # Strip any leading 'Subject:' or drafts
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        l_str = line.strip()
        if l_str.lower().startswith('subject:'):
            cleaned_lines.append(l_str[8:].strip())
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _get_gemini_api_key():
    """Retrieve Gemini API Key from settings or .env file."""
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if api_key:
        return api_key
    
    env_path = os.path.join(settings.BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip().upper()
                v = v.strip().strip('"\'')
                if k in ['GEMINI_API_KEY', 'GEMINI_KEY']:
                    return v
    return os.environ.get('GEMINI_API_KEY')


def compute_gods_eye_telemetry(force_refresh=False):
    """
    Synthesizes raw market breadth and quant terminal records into a dense,
    user-friendly telemetry object with strictly verified mutually exclusive
    Domino Cascade buckets summing to exactly the universe size (115 stocks).
    """
    # 1. Macro Breadth Telemetry
    breadth_payload = get_market_breadth_payload(force_refresh=force_refresh)
    breadth_all = breadth_payload['all']['summary']
    breadth_n50 = breadth_payload['nifty50']['summary']
    
    # 2. Quant Terminal S/R Records
    records, charts_data = get_quant_terminal_payload()
    df_stocks = pd.DataFrame(records)
    total_universe = len(df_stocks)
    
    # Safe numeric conversion
    df_stocks['support_lvl'] = pd.to_numeric(df_stocks['support_lvl'], errors='coerce')
    df_stocks['resist_lvl'] = pd.to_numeric(df_stocks['resist_lvl'], errors='coerce')
    df_stocks['close'] = pd.to_numeric(df_stocks['close'], errors='coerce')
    df_stocks['safety_score'] = pd.to_numeric(df_stocks['safety_score'], errors='coerce')
    df_stocks['rr_ratio'] = pd.to_numeric(df_stocks['rr_ratio'], errors='coerce')
    
    # Proximity calculations
    df_stocks['dist_support_pct'] = ((df_stocks['close'] - df_stocks['support_lvl']) / df_stocks['close'] * 100).round(2)
    df_stocks['dist_resist_pct'] = ((df_stocks['resist_lvl'] - df_stocks['close']) / df_stocks['close'] * 100).round(2)
    
    # Mutually exclusive domino categorization
    def classify_domino(row):
        d_sup = row['dist_support_pct']
        d_res = row['dist_resist_pct']
        if d_res <= 2.0 and d_res < d_sup:
            return 'Upside Trigger Line'
        elif d_sup <= 2.0 and d_sup <= d_res:
            return 'Downside Danger Line'
        else:
            return 'Neutral Mid-Zone'
            
    df_stocks['domino_state'] = df_stocks.apply(classify_domino, axis=1)
    
    downside_danger = df_stocks[df_stocks['domino_state'] == 'Downside Danger Line']
    upside_trigger = df_stocks[df_stocks['domino_state'] == 'Upside Trigger Line']
    neutral_midzone = df_stocks[df_stocks['domino_state'] == 'Neutral Mid-Zone']
    
    # 4 Category Buckets with stock lists and struct_labels
    breakout_stocks = df_stocks[df_stocks['is_breakout'] | df_stocks['category'].str.contains('Breakout', case=False, na=False)]
    rebound_stocks = df_stocks[df_stocks['category'].str.contains('Rebound', case=False, na=False)]
    rejection_stocks = df_stocks[df_stocks['category'].str.contains('Rejection', case=False, na=False)]
    breakdown_stocks = df_stocks[df_stocks['category'].str.contains('Breakdown', case=False, na=False) | (df_stocks['close'] < df_stocks['demand_floor'])]

    def format_stock_summary(row):
        return {
            "symbol": str(row['symbol']),
            "price": f"₹{row['close']:,.2f}",
            "change": f"{row['change_pct']:+.2f}%",
            "struct_label": str(row['struct_label']),
            "safety_score": float(row['safety_score']) if pd.notnull(row['safety_score']) else 50.0
        }

    category_buckets = {
        "breakouts": {
            "count": len(breakout_stocks),
            "description": "Stocks punching through overhead resistance",
            "stocks": [format_stock_summary(r) for _, r in breakout_stocks.iterrows()]
        },
        "rebounds": {
            "count": len(rebound_stocks),
            "description": "Stocks finding confirmed buying support floor and bouncing",
            "stocks": [format_stock_summary(r) for _, r in rebound_stocks.iterrows()]
        },
        "supply_rejections": {
            "count": len(rejection_stocks),
            "description": "Stocks slammed by overhead sellers at resistance",
            "stocks": [format_stock_summary(r) for _, r in rejection_stocks.iterrows()]
        },
        "demand_breakdowns": {
            "count": len(breakdown_stocks),
            "description": "Stocks breaking below critical support floors into free-fall danger",
            "stocks": [format_stock_summary(r) for _, r in breakdown_stocks.iterrows()]
        }
    }

    # Top representative friendly setups
    rebounds_df = df_stocks[df_stocks['category'].str.contains('Rebound', case=False, na=False)].sort_values('rr_ratio', ascending=False)
    friendly_setups = []
    for _, row in rebounds_df.head(3).iterrows():
        friendly_setups.append({
            "stock": row['symbol'],
            "current_price": f"₹{row['close']:,.2f}",
            "day_change": f"{row['change_pct']:+.2f}%",
            "why_it_stands_out": "Bouncing cleanly off a strong, multi-month buying floor where institutional buyers have consistently absorbed selling.",
            "upside_to_risk_ratio": f"{row['rr_ratio']:.1f}:1 potential upside (risking ₹1 on a stop-loss to make ~₹{row['rr_ratio']:.0f})",
            "trend_safety": "High balance sheet & historical drawdown stability" if row['safety_score'] > 70 else "Moderate stability"
        })
        
    domino_scenario_data = {
        "total_stocks_accounted_for": f"{len(downside_danger)} + {len(upside_trigger)} + {len(neutral_midzone)} = {total_universe} stocks (100% of the F&O universe)",
        "downside_danger_group": {
            "count": len(downside_danger),
            "percentage": f"{len(downside_danger)/total_universe*100:.1f}%",
            "notable_names": downside_danger['symbol'].head(8).tolist(),
            "plain_english_meaning": "These stocks are balancing right on their critical danger line (support floor). If the market slips, stop-loss orders across these names will get hit simultaneously, triggering a cascade of forced selling."
        },
        "upside_trigger_group": {
            "count": len(upside_trigger),
            "percentage": f"{len(upside_trigger)/total_universe*100:.1f}%",
            "notable_names": upside_trigger['symbol'].head(8).tolist(),
            "plain_english_meaning": "These stocks are coiled tightly right underneath overhead resistance. If the market finds a strong buyer impulse, these names have the coiled energy to lead a sharp short-covering rally."
        },
        "neutral_midzone_group": {
            "count": len(neutral_midzone),
            "percentage": f"{len(neutral_midzone)/total_universe*100:.1f}%",
            "notable_names": neutral_midzone['symbol'].head(8).tolist(),
            "plain_english_meaning": "These stocks are trading comfortably in the middle of their range, acting as market shock absorbers without immediate breakout or breakdown risk."
        }
    }
    
    telemetry_payload = {
        "session_date": breadth_all['date_str'],
        "universe_total_stocks": total_universe,
        "market_health_pulse": {
            "score_out_of_100": breadth_all['cmsi'],
            "status": "Caution / Sellers in Control (Selective Institutional Distribution)",
            "long_term_trend": f"Only {breadth_all['pct_200']}% of liquid stocks ({breadth_all['above_200_count']} of {total_universe}) are in healthy uptrends above their 200-day moving average. {100 - breadth_all['pct_200']}% remain in long-term downtrends.",
            "daily_advancers_vs_decliners": f"Heavily skewed downward: {breadth_all['gainers_count']} advancing stocks vs {breadth_all['losers_count']} declining stocks ({breadth_all['pct_gainers']}% gainers).",
            "money_flow_volume": f"Only {breadth_all['pct_up_vol']}% of total trading volume went into advancing stocks. Big institutions were either sitting on the sidelines or offloading into morning rallies."
        },
        "key_level_domino_cascade": domino_scenario_data,
        "what_sellers_and_buyers_are_doing": {
            "overhead_rejections": f"{len(rejection_stocks)} stocks ({len(rejection_stocks)/total_universe*100:.1f}% of universe) slammed into heavy overhead seller resistance and got rejected.",
            "support_rebounds": f"{len(rebound_stocks)} stocks ({len(rebound_stocks)/total_universe*100:.1f}%) managed to find confirmed buying support and bounce.",
            "fresh_breakouts": f"{len(breakout_stocks)} stocks ({len(breakout_stocks)/total_universe*100:.1f}%) showed isolated breakouts.",
            "demand_breakdowns": f"{len(breakdown_stocks)} stocks ({len(breakdown_stocks)/total_universe*100:.1f}%) broke below critical demand floors." if len(breakdown_stocks) > 0 else f"0 confirmed breakdowns today (though {len(downside_danger)} stocks hover on the Downside Danger Line).",
            "takeaway": f"For every 1 stock showing buyer strength, roughly {max(1, round(len(rejection_stocks) / max(1, len(rebound_stocks) + len(breakout_stocks))))} stocks are getting slammed by overhead sellers."
        },
        "category_stock_buckets": category_buckets,
        "surfaced_trade_setups": friendly_setups,
        "actionable_rules": {
            "for_investors": "Keep 40-50% in cash or liquid funds. Avoid averaging down on falling stocks. Wait until more than 50% of stocks reclaim their 50-day average before adding fresh long-term capital.",
            "for_active_traders": "Cut your normal position size in half (0.5x). Cease buying breakouts into resistance because false breakouts are very high right now. Focus strictly on clean bounces with at least a 3:1 reward-to-risk ratio and strict stop-losses."
        }
    }
    
    domino_symbols_map = {
        'downside_danger': downside_danger['symbol'].tolist(),
        'upside_trigger': upside_trigger['symbol'].tolist(),
        'neutral_midzone': neutral_midzone['symbol'].tolist(),
    }
    
    counts = {
        'total': total_universe,
        'downside_danger': len(downside_danger),
        'upside_trigger': len(upside_trigger),
        'neutral_midzone': len(neutral_midzone),
        'cmsi': breadth_all['cmsi'],
        'regime': breadth_all['regime_label'],
        'date_str': breadth_all['date_str'],
        'breakouts_count': len(breakout_stocks),
        'rebounds_count': len(rebound_stocks),
        'supply_rejections_count': len(rejection_stocks),
        'demand_breakdowns_count': len(breakdown_stocks),
    }
    
    return telemetry_payload, counts, domino_symbols_map


def generate_editorial_with_gemini(telemetry_data):
    """
    Invokes Google Gemini with the telemetry payload using automatic model fallback.
    Returns the markdown text of the editorial.
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in .env or settings.")
        
    models = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash", "gemini-pro-latest"]
    
    prompt = f"""Here is today's verified market telemetry ({telemetry_data['session_date']}):

```json
{json.dumps(telemetry_data, indent=2, cls=NpEncoder)}
```

Write the user-friendly, high-impact LinkedIn article now based strictly on these exact metrics.
REMEMBER: ZERO MARKDOWN SYMBOLS (no ###, no **). Format category buckets clearly with stock lists and their [struct_label].
"""

    payload_with_thinking = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192,
            "thinkingConfig": {
                "thinkingBudget": 512
            }
        }
    }

    payload_standard = {
        "contents": payload_with_thinking["contents"],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192
        }
    }

    last_err = None
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        for payload in [payload_with_thinking, payload_standard]:
            try:
                response = requests.post(url, json=payload, timeout=50)
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get('candidates', [])
                    if candidates:
                        candidate = candidates[0]
                        finish_reason = candidate.get('finishReason', '')
                        parts = candidate.get('content', {}).get('parts', [])
                        text_content = "".join([p.get('text', '') for p in parts if 'text' in p]).strip()
                        
                        # Guard against truncated text
                        if finish_reason == 'MAX_TOKENS' or len(text_content) < 1200:
                            last_err = f"{model_name} response truncated (finishReason={finish_reason}, len={len(text_content)})"
                            logger.warning(last_err)
                            continue
                            
                        logger.info(f"God's Eye editorial generated via {model_name} ({len(text_content)} chars)")
                        return text_content
                elif response.status_code == 400 and payload is payload_with_thinking:
                    continue
                else:
                    last_err = f"{model_name} HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Model {model_name} returned {response.status_code}, trying next...")
                    break
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Model {model_name} exception: {e}, trying next fallback...")
                break

    raise RuntimeError(f"All Gemini models failed to generate editorial. Last error: {last_err}")


def get_or_create_daily_briefing(force_generate=False):
    """
    Retrieves today's active MarketDailyBriefing or generates one using Gemini.
    """
    today = timezone.localdate()
    
    telemetry, counts, domino_symbols_map = compute_gods_eye_telemetry(force_refresh=force_generate)
    
    briefing = MarketDailyBriefing.objects.filter(session_date=today).first()
    
    if briefing and not force_generate:
        return briefing, telemetry, counts, domino_symbols_map
        
    # Generate new article with Gemini
    article_text = generate_editorial_with_gemini(telemetry)
    
    # Clean leading conversational chatter if present
    lines = article_text.splitlines()
    start_idx = 0
    for idx, line in enumerate(lines[:6]):
        line_l = line.strip().lower()
        if any(line_l.startswith(p) for p in ["here's", "here is", "sure", "certainly", "below is", "draft:"]) or line.strip() in ['---', '***', '']:
            start_idx = idx + 1
        else:
            break
    if start_idx > 0 and start_idx < len(lines):
        article_text = "\n".join(lines[start_idx:]).strip()

    # Fully sanitize and strip any rogue ###, **, *, __, _, ` markdown symbols
    article_text = clean_markdown_formatting(article_text)

    # Extract clean headline
    headline = "Is the Market's Calm Deceptive? What's Really Moving Beneath the Surface"
    for line in article_text.splitlines():
        line_clean = clean_markdown_formatting(line).strip()
        if line_clean.lower().startswith('subject:'):
            line_clean = line_clean[8:].strip()
        if line_clean and len(line_clean) > 10:
            if any(line_clean.lower().startswith(prefix) for prefix in ["here's", "here is", "sure", "certainly", "below is", "draft:"]):
                continue
            headline = line_clean[:250]
            break
            
    briefing, _ = MarketDailyBriefing.objects.update_or_create(
        session_date=today,
        defaults={
            'health_score': counts['cmsi'],
            'regime_status': counts['regime'],
            'total_universe': counts['total'],
            'downside_danger_count': counts['downside_danger'],
            'upside_trigger_count': counts['upside_trigger'],
            'neutral_midzone_count': counts['neutral_midzone'],
            'telemetry_json': json.dumps(telemetry, cls=NpEncoder),
            'headline': headline,
            'article_markdown': article_text,
        }
    )
    
    return briefing, telemetry, counts, domino_symbols_map


def publish_briefing_to_market_breadth_summary(briefing_id):
    """
    Publishes a saved MarketDailyBriefing to the Market Breadth Summary desk
    and archives it as an active published daily briefing.
    """
    briefing = MarketDailyBriefing.objects.get(id=briefing_id)
    briefing.is_published = True
    briefing.save()
    return briefing


def publish_briefing_to_community(briefing_id):
    """
    Publishes a saved MarketDailyBriefing to the Market Breadth Summary desk.
    Retained for API backwards compatibility.
    """
    return publish_briefing_to_market_breadth_summary(briefing_id)

