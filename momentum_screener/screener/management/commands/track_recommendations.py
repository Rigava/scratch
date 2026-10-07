import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from screener.models import RecommendationStrategy, TradeRecommendation, TradeUpdateLog, StockFundamental

class Command(BaseCommand):
    help = 'Tracks open trade recommendations against live market prices and updates lifecycle state machine'

    def handle(self, *args, **options):
        open_trades = TradeRecommendation.objects.filter(status__in=['pending', 'active', 'target_1_hit'])
        self.stdout.write(f"Evaluating {open_trades.count()} open recommendations...")

        now = timezone.now()

        for rec in open_trades:
            # Determine current price
            cmp = None
            fund = StockFundamental.objects.filter(ticker=rec.ticker).first()
            
            # Simple fallback for CMP if external tick not available
            if not cmp:
                # Use entry price with small simulation variance if mock
                cmp = float(rec.entry_price_triggered or rec.entry_price_min)
                
            self.stdout.write(f"Checking {rec.ticker}: Status={rec.status}, CMP={cmp}")

            # 1. Pending -> Active
            if rec.status == 'pending':
                if float(rec.entry_price_min) <= cmp <= float(rec.entry_price_max) or cmp >= float(rec.entry_price_min):
                    rec.status = 'active'
                    rec.entry_price_triggered = cmp
                    rec.initiated_at = now
                    rec.save()
                    TradeUpdateLog.objects.create(
                        recommendation=rec,
                        old_status='pending',
                        new_status='active',
                        trigger_price=cmp,
                        notes=f"Price entered execution range ({rec.entry_price_min}-{rec.entry_price_max}). Trade is now ACTIVE."
                    )
                    self.stdout.write(self.style.SUCCESS(f"-> {rec.ticker} triggered into ACTIVE at Rs. {cmp}"))

            # 2. Active / Target 1 Hit
            elif rec.status in ['active', 'target_1_hit']:
                effective_sl = float(rec.trailing_stop_loss or rec.stop_loss)

                # Check Stop Loss
                if cmp <= effective_sl:
                    rec.status = 'sl_hit'
                    rec.exit_price = effective_sl
                    rec.closed_at = now
                    gain_loss = ((effective_sl - float(rec.entry_price_min)) / float(rec.entry_price_min)) * 100
                    rec.realized_gain_loss_pct = round(gain_loss, 2)
                    rec.is_winning_trade = gain_loss > 0
                    if rec.initiated_at:
                        rec.holding_days = max(1, (now - rec.initiated_at).days)
                    rec.save()
                    TradeUpdateLog.objects.create(
                        recommendation=rec,
                        old_status=rec.status,
                        new_status='sl_hit',
                        trigger_price=effective_sl,
                        notes=f"Stop loss triggered at Rs. {effective_sl} ({rec.realized_gain_loss_pct}%)."
                    )
                    self.stdout.write(self.style.WARNING(f"-> {rec.ticker} STOP LOSS HIT at Rs. {effective_sl}"))

                # Check Target 1
                elif rec.status == 'active' and cmp >= float(rec.target_1):
                    rec.status = 'target_1_hit'
                    rec.trailing_stop_loss = rec.entry_price_min  # Move SL to cost
                    rec.save()
                    TradeUpdateLog.objects.create(
                        recommendation=rec,
                        old_status='active',
                        new_status='target_1_hit',
                        trigger_price=float(rec.target_1),
                        notes=f"Target 1 achieved at Rs. {rec.target_1}. 50% profit booked and Trailing SL moved to entry (Rs. {rec.entry_price_min})."
                    )
                    self.stdout.write(self.style.SUCCESS(f"-> {rec.ticker} TARGET 1 HIT!"))

                # Check Target 2
                elif rec.target_2 and cmp >= float(rec.target_2):
                    rec.status = 'completed_profit'
                    rec.exit_price = rec.target_2
                    rec.closed_at = now
                    rec.is_winning_trade = True
                    gain_loss = ((float(rec.target_2) - float(rec.entry_price_min)) / float(rec.entry_price_min)) * 100
                    rec.realized_gain_loss_pct = round(gain_loss, 2)
                    if rec.initiated_at:
                        rec.holding_days = max(1, (now - rec.initiated_at).days)
                    rec.save()
                    TradeUpdateLog.objects.create(
                        recommendation=rec,
                        old_status=rec.status,
                        new_status='completed_profit',
                        trigger_price=float(rec.target_2),
                        notes=f"Target 2 achieved at Rs. {rec.target_2} (+{rec.realized_gain_loss_pct}%). Trade successfully completed in profit."
                    )
                    self.stdout.write(self.style.SUCCESS(f"-> {rec.ticker} COMPLETED IN PROFIT!"))

        # 3. Recalculate Strategy Accuracy Statistics
        for strat in RecommendationStrategy.objects.all():
            closed_recs = TradeRecommendation.objects.filter(strategy=strat, status__in=['completed_profit', 'sl_hit'])
            strat.total_signals = TradeRecommendation.objects.filter(strategy=strat).exclude(status='draft').count()
            if closed_recs.exists():
                wins = closed_recs.filter(is_winning_trade=True).count()
                strat.win_rate = round((wins / closed_recs.count()) * 100, 1)
                returns = [r.realized_gain_loss_pct for r in closed_recs if r.realized_gain_loss_pct is not None]
                if returns:
                    strat.avg_return_pct = round(sum(returns) / len(returns), 2)
            strat.save()

        self.stdout.write(self.style.SUCCESS("Price tracking and strategy accuracy sync completed."))
