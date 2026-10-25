import os
import sys
import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from screener.gods_eye_service import (
    compute_gods_eye_telemetry,
    get_or_create_daily_briefing,
    publish_briefing_to_community
)

class Command(BaseCommand):
    help = "TradeKriya God's Eye Agent: Stitches macro breadth, supply/demand screeners, and domino cascade levels into a daily LinkedIn editorial."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force regenerate new editorial using Gemini even if one exists for today.')
        parser.add_argument('--publish', action='store_true', help='Automatically publish briefing to TradeKriya Community feed.')

    def handle(self, *args, **options):
        force_generate = options.get('force', False)
        auto_publish = options.get('publish', False)

        self.stdout.write(self.style.NOTICE(f"[START] Running God's Eye Market Intelligence Agent (Force: {force_generate})..."))

        try:
            briefing, telemetry, counts, domino_symbols_map = get_or_create_daily_briefing(force_generate=force_generate)
            
            self.stdout.write(self.style.SUCCESS(f"[SUCCESS] Briefing ID: {briefing.id} | Date: {briefing.session_date}"))
            clean_hl = briefing.headline.encode('ascii', errors='replace').decode('ascii')
            self.stdout.write(self.style.NOTICE(f"Headline: {clean_hl}"))
            self.stdout.write(f"Domino Cascade Breakdown: {counts['downside_danger']} Danger | {counts['upside_trigger']} Trigger | {counts['neutral_midzone']} Neutral (Total: {counts['total']})")
            
            if auto_publish:
                if not briefing.is_published:
                    post = publish_briefing_to_community(briefing.id)
                    self.stdout.write(self.style.SUCCESS(f"[PUBLISHED] Created Community Post ID: {post.id}"))
                else:
                    self.stdout.write(self.style.WARNING(f"[INFO] Briefing was already published."))

            self.stdout.write(self.style.SUCCESS("[DONE] God's Eye Agent completed successfully."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Failed to run God's Eye Agent: {e}"))
            sys.exit(1)
