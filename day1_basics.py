# DAY 1: Python syntax, mapped against Java you already know.
# Run this whole file with:  python day1_basics.py
# Read the comments, then scroll to the bottom for your task.

# --- Variables ---
# Java:   int age = 17;         String name = "Alex";
# Python: no type keyword, no semicolon. Type is inferred at runtime.
age = 45
name = "John"

# --- Printing ---
# Java:   System.out.println("Hello " + name);
# Python: print(), and f-strings (f"...") let you embed variables directly.
print(f"Hello {name}, you are {age}")

# --- Blocks: indentation IS the syntax, not {} ---
# Java:   if (age >= 18) { System.out.println("adult"); } else { ... }
# Python: colon starts a block, indentation (4 spaces) defines what's inside it.
if age >= 18:
    print("adult")
else:
    print("minor")

# --- Lists (like ArrayList<String>) ---
agents = ["Jett", "Sova", "Killjoy"]
agents.append("Reyna")
print(agents)          # ['Jett', 'Sova', 'Killjoy', 'Reyna']
print(agents[0])       # "Jett"  -- indexing works the same as Java arrays

# --- Looping over a list ---
# Java:   for (String a : agents) { System.out.println(a); }
# Python: for-each is the DEFAULT for loop style. No index unless you ask for one.
for a in agents:
    print(f"agent: {a}")

# --- Dicts (like HashMap<String, Integer>) ---
win_rates = {"Jett": 48, "Sova": 51, "Killjoy": 53}
print(win_rates["Sova"])          # 51
win_rates["Reyna"] = 45           # add a new key, just like map.put(...)

for agent, rate in win_rates.items():
    print(f"{agent}: {rate}%")

# --- Functions ---
# Java:   public static int addBonus(int rate, int bonus) { return rate + bonus; }
# Python: def, no return type declared, no access modifier.
def add_bonus(rate, bonus=5):     # bonus=5 is a DEFAULT value (Java needs overloads for this)
    return rate + bonus

print(add_bonus(51))       # 56  (uses default bonus=5)
print(add_bonus(51, 10))   # 61

# ============================================================
# YOUR TASK:
# 1. Add "Omen" to the agents list with win_rates["Omen"] = 49
# 2. Write a function `best_agent(rates_dict)` that returns the
#    agent name with the highest win rate. (Hint: look up max() with key=)
# 3. Print the result.
# ============================================================
