# 🩺 SQL Doctor

Paste a PostgreSQL query that failed and the error it gave you. SQL Doctor explains what went wrong in plain words, points to the exact part of the query that broke, and shows the fixed query. It can explain in English, Hinglish or Gujarati.

I built it for my DBMS lab classmates, who lose a lot of lab time staring at errors like `column "x" must appear in the GROUP BY clause`.

It runs entirely on your own laptop with **Gemma 4**, an open-weight model, through **Ollama**. Your queries never leave your machine, it works without internet, and it costs nothing to run.

## Run it

1. Install [Ollama](https://ollama.com) and download the model:

   ```bash
   ollama pull gemma4:e4b
   ```

   On a slower laptop, use `gemma4:e2b` instead and change the model name in the app's sidebar.

2. Install the Python packages:

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Start the app:

   ```bash
   streamlit run app.py
   ```

   It opens in your browser at http://localhost:8501. Pick an example from the dropdown or paste your own query and error, then click **Diagnose**.

## How it works

The app sends your query, the error, and (optionally) your `CREATE TABLE` statements to Gemma 4 running locally in Ollama. A system prompt asks the model to answer in four fixed sections (what went wrong, where, the fixed query, and a tip for next time), to change only what's needed, and to say so when it isn't sure instead of guessing. The answer streams into the page as it's generated.

Built for the [Hacktoberfest Weekend Challenge: Build for a Friend](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01).
