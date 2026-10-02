# M-Pesa Expense Tracker

A Streamlit app that turns your M-Pesa PDF statements into a private, per-user dashboard:
spending by category, payees, recurring payments, anomalies, budgets, a forecast and exports.
Data is stored in Supabase with row-level security.

## Setup

1. **Supabase**: create a project, enable Email auth, create your user.
   Run `schema.sql` in the SQL editor (adds `balance`, the `mpesa_category_rules` table, and RLS policies).
2. **Secrets**: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in
   `SUPABASE_URL` and the **anon** key (never `service_role`).
3. **Run**
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
4. **Tests**: `pip install -r requirements-dev.txt && pytest -q`

## Folder layout

```
app.py              auth, upload -> parse -> save -> load, navigation
db.py               Supabase layer (per-session client, token refresh, pagination, verified writes)
ui_helpers.py       get_df(), layout helpers, Streamlit-version compatibility
parsers/mpesa.py    PDF text -> rows; skips page furniture; keeps balance; reconciliation check
analytics/          common (enrich, internal flows), categories, metrics, anomalies, recurring, forecast
pages/              one file per dashboard page
tests/              parser + analytics tests
schema.sql          migration + RLS policies
```

## Concepts

* **Reconciliation badge**: after each upload the running balance is checked against the amounts.
  A green tick means the parse is trustworthy; a warning lists the rows that don't add up.
* **Internal movements** (Fuliza repayments, M-Shwari, anything categorised `Internal`) are excluded
  from income, expenses and savings rate, so totals reflect real money in and out.
* **Category rules** map payee/details text to categories (Category Rules page). Unmatched
  Paybill/Merchant items show as `Uncategorised` on purpose so you can label them.
* **Re-uploading** never overwrites rows you edited, unless you tick *Overwrite existing rows*
  (do this once after a parser upgrade).
* **Sessions** live in the browser tab: refreshing the page signs you out.

## Security notes

* One Supabase client per browser session; never cache clients or user data across sessions.
* All queries filter on `user_id` in addition to RLS.
* Statements contain personal data: `*.pdf` and `*.csv` are git-ignored.