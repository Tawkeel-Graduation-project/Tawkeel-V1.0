import re

path = "consumer_protection_181_2018_part2.txt"
text = open(path, encoding="utf-8").read()   # errors out if it isn't valid UTF-8

print(text[:200])                              # does the Arabic look normal?

found = [int(n) for n in re.findall(r"مادة \((\d+)\):", text)]
print(len(found), "article headers found")

expected = list(range(3, 42))                  # 3 to 41 inclusive
print("missing:", sorted(set(expected) - set(found)))
print("duplicates/extra:", sorted(set(found) - set(expected)))