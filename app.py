"""SQL Doctor: explains PostgreSQL errors in plain words.

Runs fully offline on an open-weight model (Gemma 4) through Ollama.
"""

import html
import os
import re

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
- Keep the four section headings exactly as written above, in English, even when the rest of the answer is in another language.
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
    "Double quotes on text": (
        'SELECT name\nFROM student\nWHERE dept_name = "Comp. Sci.";',
        'ERROR:  column "Comp. Sci." does not exist\n'
        'LINE 3: WHERE dept_name = "Comp. Sci.";',
    ),
    "Ambiguous column": (
        "SELECT id, name, course_id\nFROM student\nJOIN takes ON student.id = takes.id;",
        'ERROR:  column reference "id" is ambiguous\n'
        "LINE 1: SELECT id, name, course_id",
    ),
    "Extra comma": (
        "SELECT id, name,\nFROM student;",
        'ERROR:  syntax error at or near "FROM"\nLINE 2: FROM student;',
    ),
    "Misspelled table name": (
        "SELECT *\nFROM students;",
        'ERROR:  relation "students" does not exist\nLINE 2: FROM students;',
    ),
    "Misspelled column name": (
        "SELECT name, salry\nFROM instructor;",
        'ERROR:  column "salry" does not exist\n'
        "LINE 1: SELECT name, salry\n"
        'HINT:  Perhaps you meant to reference the column "instructor.salary".',
    ),
    "Table missing from FROM": (
        "SELECT student.name, instructor.name\nFROM instructor;",
        'ERROR:  missing FROM-clause entry for table "student"\n'
        "LINE 1: SELECT student.name, instructor.name",
    ),
    "Aggregate inside WHERE": (
        "SELECT dept_name\nFROM instructor\nWHERE AVG(salary) > 50000\nGROUP BY dept_name;",
        "ERROR:  aggregate functions are not allowed in WHERE\n"
        "LINE 3: WHERE AVG(salary) > 50000",
    ),
    "Column alias used in WHERE": (
        "SELECT name, salary * 12 AS yearly\nFROM instructor\nWHERE yearly > 1000000;",
        'ERROR:  column "yearly" does not exist\nLINE 3: WHERE yearly > 1000000;',
    ),
    "Subquery returns many rows": (
        "SELECT name\nFROM instructor\nWHERE salary = (SELECT salary FROM instructor\n"
        "                WHERE dept_name = 'Physics');",
        "ERROR:  more than one row returned by a subquery used as an expression",
    ),
    "UNION column count differs": (
        "SELECT id, name FROM student\nUNION\nSELECT id FROM instructor;",
        "ERROR:  each UNION query must have the same number of columns\n"
        "LINE 3: SELECT id FROM instructor;",
    ),
    "Text in a number column": (
        "SELECT name\nFROM instructor\nWHERE salary = 'high';",
        'ERROR:  invalid input syntax for type numeric: "high"\n'
        "LINE 3: WHERE salary = 'high';",
    ),
    "Duplicate primary key": (
        "INSERT INTO department\nVALUES ('Biology', 'Watson', 90000);",
        'ERROR:  duplicate key value violates unique constraint "department_pkey"\n'
        "DETAIL:  Key (dept_name)=(Biology) already exists.",
    ),
    "Foreign key not found": (
        "INSERT INTO instructor\nVALUES ('99999', 'Sharma', 'Robotics', 70000);",
        'ERROR:  insert or update on table "instructor" violates foreign key '
        'constraint "instructor_dept_name_fkey"\n'
        'DETAIL:  Key (dept_name)=(Robotics) is not present in table "department".',
    ),
    "Reserved word as table name": (
        "CREATE TABLE user (\n  id INT PRIMARY KEY,\n  name VARCHAR(20)\n);",
        'ERROR:  syntax error at or near "user"\nLINE 1: CREATE TABLE user (',
    ),
}

# The model writes plain "### Heading" lines; once the answer is complete they
# become small badges. Red and green are status colours only: what broke, and
# what fixes it. Everything else stays neutral.
SECTION_BADGES = {
    "What went wrong": ":red-badge[What went wrong]",
    "Where": ":gray-badge[Where]",
    "Fixed query": ":green-badge[Fixed query]",
    "Remember next time": ":gray-badge[Remember next time]",
}

# Line icon in Netra's style: thin stroke, no fill. No emoji anywhere.
LOGO_SVG = (
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" '
    'stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<ellipse cx="11" cy="5.5" rx="7" ry="2.5"/><path d="M4 5.5v12c0 1.4 3.1 2.5 7 2.5"/>'
    '<path d="M18 5.5v5"/><path d="M4 11.5c0 1.4 3.1 2.5 7 2.5"/>'
    '<path d="M18 14v6"/><path d="M15 17h6"/></svg>'
)

CSS = """
<style>
:root {
  /* Neutrals are mixed from the theme's own text colour, so they follow
     Streamlit's Light/Dark switch with no extra code. Ratios against the page:
     rule ~1.5:1 (decorative only), outline >= 3:1, muted text >= 5.5:1. */
  --sd-rule: color-mix(in srgb, currentColor 20%, transparent);
  --sd-outline: color-mix(in srgb, currentColor 50%, transparent);
  --sd-muted: color-mix(in srgb, currentColor 68%, transparent);
  --sd-ok: #2E9E4F;  /* >= 3:1 on both the light and dark backgrounds */
  --sd-mark: #FFD43B; --sd-ink-on-mark: #241C00;
  --sd-serif: Literata, Georgia, "Times New Roman", serif;
  --sd-mono: Poppins, sans-serif; }
.sd-top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 12px; padding-bottom: 14px; margin-bottom: 8px; border-bottom: 1px solid var(--sd-rule); }
.sd-brand { display: flex; align-items: center; gap: 10px;
  font-family: var(--sd-serif); font-size: 22px; font-weight: 600; letter-spacing: -0.01em; }
.sd-pill { display: inline-flex; align-items: center; gap: 8px; padding: 5px 12px;
  border: 1px solid var(--sd-rule); border-radius: 999px; font-size: 13px; }
.sd-dot { width: 8px; height: 8px; border-radius: 999px; background: var(--sd-ok); }
.sd-mono { font-family: var(--sd-mono); font-size: 12.5px; }
.sd-muted { color: var(--sd-muted); }
.sd-hero { margin: 28px 0 28px; max-width: 760px; }
.sd-hero h1 { font-family: var(--sd-serif); font-optical-sizing: auto;
  font-size: clamp(34px, 5vw, 50px); line-height: 1.12; font-weight: 600;
  letter-spacing: -0.02em; margin: 0 0 14px; padding: 0; text-wrap: balance; }
.sd-hero p { font-size: 17px; line-height: 1.6; margin: 0; max-width: 620px; color: var(--sd-muted); }
/* Netra's hero marker: a signal-yellow band behind one phrase, dark ink on top. */
.sd-mark { position: relative; display: inline-block; padding: 0 0.22em; isolation: isolate;
  color: var(--sd-ink-on-mark); }
.sd-mark::before { content: ""; position: absolute; top: 0.11em; bottom: -0.11em; left: 0; right: 0;
  border-radius: 0.5rem; background: var(--sd-mark); z-index: -1; }
/* Queries, errors and CREATE TABLEs are code: show them in the code font. */
.st-key-query textarea, .st-key-error textarea, .st-key-schema textarea {
  font-family: var(--sd-mono); font-size: 13.5px; line-height: 1.6; }
.sd-empty { min-height: 320px; border: 1px dashed var(--sd-outline); border-radius: 12px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  padding: 24px; text-align: center; }
.sd-empty p { margin: 0; }
.sd-foot { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--sd-rule);
  display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; font-size: 13px; }
</style>
"""


def load_example() -> None:
    choice = st.session_state.example
    if choice in EXAMPLES:
        st.session_state.query, st.session_state.error = EXAMPLES[choice]
        st.session_state.answer = None


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


def style_sections(text: str) -> str:
    for title, badge in SECTION_BADGES.items():
        pattern = rf"^[ \t]*#{{1,6}}[ \t]*\**{re.escape(title)}\**[ \t]*:?[ \t]*$"
        text = re.sub(pattern, badge + "\n", text, flags=re.MULTILINE | re.IGNORECASE)
    return text


st.set_page_config(
    page_title="SQL Doctor",
    page_icon=":material/database:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.html(CSS)

st.session_state.setdefault("answer", None)

with st.sidebar:
    st.subheader("Settings")
    st.text_input(
        "Ollama model",
        value=DEFAULT_MODEL,
        key="model",
        help="Switch to gemma4:e2b if answers are slow on your laptop.",
    )
    st.caption(
        "Runs entirely on this laptop with an open-weight model. Your queries never "
        "leave your machine, it works without internet, and it costs nothing."
    )

model = st.session_state.model.strip() or DEFAULT_MODEL

st.html(
    f"""
    <div class="sd-top">
      <div class="sd-brand">{LOGO_SVG}<span>SQL Doctor</span></div>
      <div class="sd-pill">
        <span class="sd-dot"></span>
        <span>Running on this laptop</span>
        <span class="sd-muted">·</span>
        <span class="sd-mono">{html.escape(model)}</span>
      </div>
    </div>
    <section class="sd-hero">
      <h1>Understand any PostgreSQL error <span class="sd-mark"><span>in plain words.</span></span></h1>
      <p>Paste the query that failed and the error it printed. SQL Doctor shows what went wrong,
      where it broke and the fixed query. Nothing leaves your laptop.</p>
    </section>
    """
)

left, right = st.columns(2, gap="large")

with left:
    with st.container(border=True):
        st.subheader("Your query")
        st.selectbox(
            "Try a common mistake",
            list(EXAMPLES),
            index=None,
            placeholder=f"Pick one of {len(EXAMPLES)} examples, or type to search",
            key="example",
            on_change=load_example,
        )
        st.text_area(
            "Query",
            key="query",
            height=140,
            placeholder="SELECT ... FROM ... ;",
        )
        st.text_area(
            "Error from PostgreSQL",
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
        st.segmented_control(
            "Explain it in",
            list(LANGUAGES),
            default="English",
            required=True,
            key="lang",
        )
        diagnose = st.button(
            "Diagnose",
            type="primary",
            icon=":material/search:",
            width="stretch",
        )

language = st.session_state.get("lang") or "English"

with right:
    with st.container(border=True):
        st.subheader("Diagnosis")
        language_name = "Gujarati" if "Gujarati" in language else language
        st.caption(f"{language_name} · Gemma 4 on this laptop")
        output = st.empty()

        if diagnose:
            query = st.session_state.get("query", "").strip()
            error = st.session_state.get("error", "").strip()
            schema = st.session_state.get("schema", "").strip()

            if not query or not error:
                output.warning("Paste both your query and the error message first.")
            else:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT.format(language=LANGUAGES[language])},
                    {"role": "user", "content": build_message(query, error, schema)},
                ]
                try:
                    full = output.write_stream(stream_reply(model, messages))
                    if isinstance(full, str) and full.strip():
                        st.session_state.answer = style_sections(full)
                        output.markdown(st.session_state.answer)
                except ollama.ResponseError as e:
                    if e.status_code == 404:
                        output.error(
                            f"The model `{model}` isn't downloaded yet. Run this in a terminal, "
                            f"then try again:\n\n`ollama pull {model}`"
                        )
                    else:
                        output.error(f"Ollama returned an error: {e.error}")
                except Exception:
                    output.error(
                        "Can't reach Ollama. Make sure the Ollama app is running "
                        "(or run `ollama serve` in a terminal), then try again."
                    )
        elif st.session_state.answer:
            output.markdown(st.session_state.answer)
        else:
            output.html(
                """
                <div class="sd-empty">
                  <p style="font-size: 15px;">Click Diagnose to see what went wrong.</p>
                  <p class="sd-muted" style="font-size: 13px;">The answer streams in as Gemma writes it.</p>
                </div>
                """
            )

st.html(
    """
    <div class="sd-foot sd-muted">
      <span>Built for my DBMS lab classmates</span>
      <span>Gemma 4 · Ollama · runs offline</span>
    </div>
    """
)
