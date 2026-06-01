"""A flat, function-free script: analyze a list of numbers, write a report.

No functions or classes — just top-level statements with loops and branches,
so the trace is a single frame. Good for exercising the player's loop/branch
highlighting without any call-stack reconstruction.
"""

readings = [12, 47, 3, 88, 21, 47, 5, 60, 47, 19, 88, 34]

count = 0
total = 0
minimum = readings[0]
maximum = readings[0]

for value in readings:
    count += 1
    total += value
    if value < minimum:
        minimum = value
    if value > maximum:
        maximum = value

mean = total / count

# Count how often each reading appears (no Counter — keep it explicit).
frequency = {}
for value in readings:
    if value in frequency:
        frequency[value] += 1
    else:
        frequency[value] = 1

most_common = None
most_common_count = 0
for value in frequency:
    if frequency[value] > most_common_count:
        most_common = value
        most_common_count = frequency[value]

# How many readings sit above the mean?
above_mean = 0
for value in readings:
    if value > mean:
        above_mean += 1

report_lines = []
report_lines.append("Reading Analysis Report")
report_lines.append("=" * 24)
report_lines.append("samples:      " + str(count))
report_lines.append("sum:          " + str(total))
report_lines.append("mean:         " + str(round(mean, 2)))
report_lines.append("minimum:      " + str(minimum))
report_lines.append("maximum:      " + str(maximum))
report_lines.append("range:        " + str(maximum - minimum))
report_lines.append("above mean:   " + str(above_mean))
report_lines.append("most common:  " + str(most_common) + " (x" + str(most_common_count) + ")")

report = "\n".join(report_lines)

with open("analysis_report.txt", "w") as handle:
    handle.write(report)
    handle.write("\n")

print(report)
