target_file = 'screener/templates/screener/index.html'
content = open(target_file, encoding='utf-8').read()

lines = content.split('\n')

# Find card start and end lines
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if '<!-- Advanced Strategy View Card -->' in line:
        start_idx = i
    if '<!-- Trade Log Modal' in line:
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print("Error: Could not locate card boundaries")
    exit(1)

# The card content goes from start_idx to end_idx - 2 (since the line before end_idx is </section> at line 1448)
print("Card starts at line:", start_idx + 1)
print("Card ends at line:", end_idx) # which is </section>

card_lines = lines[start_idx:end_idx - 1] # exclude the </section> line
card_content = '\n'.join(card_lines)

# Remove these lines from the list
del lines[start_idx:end_idx - 1]

# Now, find the index of the closing </section> of screener-results
# Let's search from the top. We know the screener-results starts at <section class="screener-results">
screener_results_start = -1
screener_results_end = -1

for i, line in enumerate(lines):
    if 'class="screener-results"' in line:
        screener_results_start = i
        break

# The closing tag of this section is the next </section> after screener_results_start
for i in range(screener_results_start + 1, len(lines)):
    if '</section>' in lines[i]:
        screener_results_end = i
        break

if screener_results_start == -1 or screener_results_end == -1:
    print("Error: Could not locate screener-results bounds")
    exit(1)

print("screener-results end tag is at line:", screener_results_end + 1)

# Insert the card content before this closing tag
lines.insert(screener_results_end, card_content)

# Write back
with open(target_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Fixed card relocation successfully!")
