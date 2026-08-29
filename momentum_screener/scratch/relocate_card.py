import re

target_file = 'screener/templates/screener/index.html'
content = open(target_file, encoding='utf-8').read()

# 1. Locate the card content from line 1279 to 1459
start_marker = "<!-- Advanced Strategy View Card -->"
end_marker = "<!-- Pro License Access Required Overlay -->"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Error: Could not find card boundaries in index.html")
    exit(1)

card_content = content[start_idx:end_idx].strip()

# 2. Delete the card content from its old position
content_deleted = content[:start_idx] + content[end_idx:]

# 3. Add table IDs and Fullscreen button in the card_content
# Add IDs to the 4 tables inside card_content
card_content = card_content.replace(
    '<table class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    '<table id="abs-ranking-table" class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    1
)
card_content = card_content.replace(
    '<table class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    '<table id="bearish-exh-table" class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    1
)
card_content = card_content.replace(
    '<table class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    '<table id="bullish-exh-table" class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    1
)
card_content = card_content.replace(
    '<table class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    '<table id="vcp-ranking-table" class="screener-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
    1
)

# Replace the Header Badge to include the Fullscreen button
old_header = """                <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); font-size: 11px; padding: 4px 8px; border-radius: 12px; font-weight: 600;">
                    <i class="fa-solid fa-crown" style="color: #fbbf24;"></i> Pro Feature
                </span>"""

new_header = """                <div style="display: flex; align-items: center; gap: 10px; margin-left: auto;">
                    <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); font-size: 11px; padding: 4px 8px; border-radius: 12px; font-weight: 600;">
                        <i class="fa-solid fa-crown" style="color: #fbbf24;"></i> Pro Feature
                    </span>
                    <button id="btn-fullscreen-advanced" class="guide-btn" title="Toggle Fullscreen Grid" style="display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; padding: 0; border-radius: var(--border-radius-sm); background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); color: var(--text-primary); cursor: pointer;">
                        <i class="fa-solid fa-expand"></i>
                    </button>
                </div>"""

card_content = card_content.replace(old_header, new_header)

# 4. Relocate the card content before the closing tag of section screener-results
# The closing tag of journal card is at </section> at line 1210 (which is the end of the screener-results section)
# Let's find:
#             </div>
#         </div>
#     </section>
#
#     <!-- Trade Log Modal
# We will insert it right before that </section>

results_section_end_pattern = """            </div>
        </div>
    </section>

    <!-- Trade Log Modal"""

replacement_insertion = """            </div>
        </div>
        
        """ + card_content + """
    </section>

    <!-- Trade Log Modal"""

content_relocated = content_deleted.replace(results_section_end_pattern, replacement_insertion, 1)

# 5. Insert the CSS rules inside the <style> block
# Let's find:
#         /* Fullscreen Screener Grid Mode overrides */
#         body.fullscreen-grid-active .app-header,
# and insert our new rules right before that.

css_insertion_point = """        /* Fullscreen Screener Grid Mode overrides */"""

new_css = """        /* Mobile Advanced Strategy Table Column Hiding */
        @media (max-width: 1024px) {
            body:not(.fullscreen-grid-active) #abs-ranking-table th:nth-child(3),
            body:not(.fullscreen-grid-active) #abs-ranking-table td:nth-child(3),
            body:not(.fullscreen-grid-active) #abs-ranking-table th:nth-child(4),
            body:not(.fullscreen-grid-active) #abs-ranking-table td:nth-child(4),
            body:not(.fullscreen-grid-active) #abs-ranking-table th:nth-child(6),
            body:not(.fullscreen-grid-active) #abs-ranking-table td:nth-child(6) {
                display: none !important;
            }

            body:not(.fullscreen-grid-active) #bearish-exh-table th:nth-child(1),
            body:not(.fullscreen-grid-active) #bearish-exh-table td:nth-child(1),
            body:not(.fullscreen-grid-active) #bearish-exh-table th:nth-child(5),
            body:not(.fullscreen-grid-active) #bearish-exh-table td:nth-child(5) {
                display: none !important;
            }

            body:not(.fullscreen-grid-active) #bullish-exh-table th:nth-child(1),
            body:not(.fullscreen-grid-active) #bullish-exh-table td:nth-child(1),
            body:not(.fullscreen-grid-active) #bullish-exh-table th:nth-child(5),
            body:not(.fullscreen-grid-active) #bullish-exh-table td:nth-child(5) {
                display: none !important;
            }

            body:not(.fullscreen-grid-active) #vcp-ranking-table th:nth-child(4),
            body:not(.fullscreen-grid-active) #vcp-ranking-table td:nth-child(4),
            body:not(.fullscreen-grid-active) #vcp-ranking-table th:nth-child(5),
            body:not(.fullscreen-grid-active) #vcp-ranking-table td:nth-child(5) {
                display: none !important;
            }
        }

        /* Fullscreen Advanced Strategy View Card overrides */
        body.fullscreen-grid-active #advanced-strategy-view-card {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 99999 !important;
            margin: 0 !important;
            border-radius: 0 !important;
            background: var(--bg-primary) !important;
            padding: 24px !important;
            box-sizing: border-box !important;
            overflow-y: auto !important;
            display: flex !important;
            flex-direction: column !important;
            gap: 16px !important;
        }

        """ + css_insertion_point

content_final = content_relocated.replace(css_insertion_point, new_css, 1)

# Write back to index.html
with open(target_file, 'w', encoding='utf-8') as f:
    f.write(content_final)

print("Relocation, CSS insertion, and ID modifications completed successfully!")
