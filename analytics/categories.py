# analytics/categories.py
"""Category vocabulary: defaults, internal-flow definitions and starter rules.

A *rule* is {"pattern": "naivas", "category": "Groceries"}. A rule matches when
its pattern appears (case-insensitive) in the payee or the details text.
Longer patterns win over shorter ones.
"""

INTERNAL_CATEGORY = "Internal"      # money moving between your own pockets
UNCATEGORISED = "Uncategorised"     # no rule matched and the type is too generic

# Types that are always internal movements, never real income/spending:
#  - Fuliza Repayment: the purchase was already counted when it happened
#  - M-Shwari: moving money between your wallet and your own savings
INTERNAL_TYPES = {"Fuliza Repayment", "M-Shwari"}

# Fallback category when no user rule matches, derived from the parsed type.
TYPE_DEFAULT_CATEGORY = {
    "Data/Airtime": "Airtime & Data",
    "Withdrawal": "Cash Withdrawal",
    "Deposit": "Cash Deposit",
    "Received": "Received from People",
    "Transfer": "People Transfers",
    "Fuliza Fee": "Fees",
    "Paybill Charge": "Fees",
    "Transfer Charge": "Fees",
    "Withdrawal Charge": "Fees",
    "Reversal": "Reversals",
    "Fuliza Repayment": INTERNAL_CATEGORY,
    "M-Shwari": INTERNAL_CATEGORY,
    # Paybill / Merchant / Other -> UNCATEGORISED on purpose, so they stand out
}

DEFAULT_CATEGORIES = [
    "Groceries", "Utilities", "Transport", "Fuel", "Rent", "Airtime & Data",
    "Eating Out", "Entertainment", "Health", "Insurance", "Education",
    "Banking & Loans", "Betting", "Shopping", "Government & Taxes",
    "Family & Friends", "Salary", "Business Income", "Savings", INTERNAL_CATEGORY,
]

# A modest starter set for Kenya. Review before use: patterns are substrings.
STARTER_RULES = [
    ("kplc", "Utilities"), ("kenya power", "Utilities"), ("nairobi water", "Utilities"),
    ("naivas", "Groceries"), ("quickmart", "Groceries"), ("carrefour", "Groceries"),
    ("chandarana", "Groceries"), ("cleanshelf", "Groceries"),
    ("uber", "Transport"), ("bolt", "Transport"), ("little cab", "Transport"),
    ("totalenergies", "Fuel"), ("rubis", "Fuel"), ("kenol", "Fuel"),
    ("netflix", "Entertainment"), ("showmax", "Entertainment"),
    ("dstv", "Entertainment"), ("gotv", "Entertainment"), ("spotify", "Entertainment"),
    ("helb", "Education"),
    ("kenya revenue", "Government & Taxes"), ("ecitizen", "Government & Taxes"),
    ("nhif", "Health"), ("social health", "Health"), ("pharmacy", "Health"),
    ("jubilee insurance", "Insurance"), ("britam", "Insurance"),
    ("equity bank", "Banking & Loans"), ("kcb", "Banking & Loans"),
    ("co-operative bank", "Banking & Loans"), ("ncba", "Banking & Loans"),
    ("stanbic", "Banking & Loans"), ("absa", "Banking & Loans"),
    ("sportpesa", "Betting"), ("betika", "Betting"), ("odibets", "Betting"),
    ("mozzart", "Betting"), ("betway", "Betting"),
]