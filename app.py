"""SQL Doctor: explains PostgreSQL errors in plain words.

Runs fully offline on an open-weight model (Gemma 4) through Ollama.
"""

import os

import ollama
import streamlit as st

DEFAULT_MODEL = os.environ.get("SQL_DOCTOR_MODEL", "gemma4:e4b")

LANGUAGES = {
    "English": "simple, friendly English",
    "Hinglish": (
        "Hinglish (casual Hindi written in English letters, the way Indian "
        "college students text each other)"
    ),
    "ગુજરાતી (Gujarati)": (
        "simple Gujarati in Gujarati script, keeping SQL keywords, table names "
        "and column names in English"
    ),
}

SYSTEM_PROMPT = """You are SQL Doctor, a patient tutor for college students in a DBMS lab who use PostgreSQL.
The student gives you their SQL query, the exact error PostgreSQL printed, and sometimes their table definitions.

Reply in {language}. Use exactly these four sections and nothing else:

### What went wrong
One or two sentences in plain words. No jargon.

### Where
Quote the exact part of the query that causes the error and explain why it breaks.

### Fixed query
The corrected query in a ```sql code block. Change only what is needed to fix the error.

### Remember next time
One short tip that would stop this mistake from happening again.

Rules:
- If the error has more than one possible cause, give the most likely one first and say what else to check.
- Never invent tables or columns the student did not mention. If you need the table definitions to be sure, say so.
- If you are unsure, say so instead of guessing."""

# Common DBMS-lab mistakes, using the university schema from the
# Silberschatz textbook that most DBMS courses use.
EXAMPLES = {
    "Forgot GROUP BY": (
        "SELECT dept_name, name, AVG(salary)\nFROM instructor\nGROUP BY dept_name;",
        'ERROR:  column "instructor.name" must appear in the GROUP BY clause '
        "or be used in an aggregate function\n"
        "LINE 1: SELECT dept_name, name, AVG(salary)",
    ),
    "Double quotes around text": (
        'SELECT name\nFROM student\nWHERE dept_name = "Comp. Sci.";',
        'ERROR:  column "Comp. Sci." does not exist\n'
        'LINE 3: WHERE dept_name = "Comp. Sci.";',
    ),
    "Ambiguous column in a JOIN": (
        "SELECT id, name, course_id\nFROM student\nJOIN takes ON student.id = takes.id;",
        'ERROR:  column reference "id" is ambiguous\n'
        "LINE 1: SELECT id, name, course_id",
    ),
    "Extra comma before FROM": (
        "SELECT id, name,\nFROM student;",
        'ERROR:  syntax error at or near "FROM"\nLINE 2: FROM student;',
    ),
}
PLACEHOLDER = "Pick a common mistake to try…"


def load_example() -> None:
    choice = st.session_state.example
    if choice in EXAMPLES:
        st.session_state.query, st.session_state.error = EXAMPLES[choice]


def build_message(query: str, error: str, schema: str) -> str:
    parts = [
        f"My query:\n```sql\n{query}\n```",
        f"PostgreSQL error:\n```\n{error}\n```",
    ]
    if schema:
        parts.append(f"My table definitions:\n```sql\n{schema}\n```")
    return "\n\n".join(parts)


def stream_reply(model: str, messages: list[dict]):
    stream = ollama.chat(
        model=model,
        messages=messages,
        stream=True,
        options={"temperature": 0.2},
    )
    for chunk in stream:
        yield chunk["message"]["content"]


st.set_page_config(page_title="SQL Doctor", page_icon="🩺")

with st.sidebar:
    st.header("Settings")
    model = st.text_input(
        "Ollama model",
        value=DEFAULT_MODEL,
        help="Switch to gemma4:e2b if answers are slow on your laptop.",
    )
    st.caption(
        "Runs 100% on this laptop with an open-weight model. Your queries never "
        "leave your machine, it works without internet, and it costs nothing."
    )

st.title("🩺 SQL Doctor")
st.write(
    "Paste a PostgreSQL query that failed and the error it gave you. "
    "SQL Doctor explains what went wrong in plain words and shows the fix."
)

st.selectbox(
    "Try an example",
    [PLACEHOLDER, *EXAMPLES],
    key="example",
    on_change=load_example,
)
st.text_area(
    "Your query",
    key="query",
    height=140,
    placeholder="SELECT ... FROM ... ;",
)
st.text_area(
    "The error PostgreSQL gave you",
    key="error",
    height=110,
    placeholder="ERROR:  ...",
)
with st.expander("Add your table definitions (optional, gives better answers)"):
    st.text_area(
        "CREATE TABLE statements",
        key="schema",
        height=140,
        placeholder="CREATE TABLE student (id VARCHAR(5) PRIMARY KEY, name VARCHAR(20), ...);",
    )

language = st.radio("Explain it in", list(LANGUAGES), horizontal=True)

if st.button("Diagnose 🩺", type="primary"):
    query = st.session_state.get("query", "").strip()
    error = st.session_state.get("error", "").strip()
    schema = st.session_state.get("schema", "").strip()

    if not query or not error:
        st.warning("Paste both your query and the error message first.")
        st.stop()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(language=LANGUAGES[language])},
        {"role": "user", "content": build_message(query, error, schema)},
    ]

    try:
        st.write_stream(stream_reply(model, messages))
    except ollama.ResponseError as e:
        if e.status_code == 404:
            st.error(
                f"The model `{model}` isn't downloaded yet. Run this in a terminal, "
                f"then try again:\n\n`ollama pull {model}`"
            )
        else:
            st.error(f"Ollama returned an error: {e.error}")
    except Exception:
        st.error(
            "Can't reach Ollama. Make sure the Ollama app is running "
            "(or run `ollama serve` in a terminal), then try again."
        )

st.divider()
st.caption("Built for my DBMS lab classmates · runs on Gemma 4 with Ollama")
