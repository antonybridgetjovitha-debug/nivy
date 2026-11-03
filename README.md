# Thunai | துணை

A bilingual (English/Tamil), accessibility-first companion prototype for older adults. It includes a GPT chat endpoint, daily check-ins, reminders, notes, and trusted contacts.

## Run locally

Requires Python 3.10 or newer. No third-party Python packages are needed.

```powershell
Set-Location 'C:\Users\Dr.Arul Deepa\Thunai'
$env:OPENAI_API_KEY = 'your-key'
python server.py
```

Open <http://127.0.0.1:8000>. Without an OpenAI API key, the app still runs; the GPT chat displays a setup message. Chat messages (including recent conversation context) are sent to OpenAI to generate replies. Check-ins are stored in `data/thunai.sqlite3`. Reminders, notes, and trusted contacts are stored in this browser's local storage.

## GitHub and personal data

Use GitHub to version the application source. Do not commit the SQLite database, real API keys, or personal care records. The `.gitignore` excludes `data/` and environment files. For a real deployment, replace local SQLite and browser storage with an authenticated, encrypted database with access controls, backups, retention rules, and consent. Configure the OpenAI key as a server environment secret. Do not expose it in frontend JavaScript.

This prototype is intended for local evaluation, not clinical or emergency use. GPT replies are not medical advice. The assistant does not contact emergency services or family members.
