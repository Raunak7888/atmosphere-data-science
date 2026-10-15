"""
make_readme.py - generates README.md with project overview, run instructions,
and an embedded project report containing every saved topic, question, graph,
and summary.

Usage (from the project root):
    python src/make_readme.py

Expected report outputs:
    reports/parts/<topic-folder>/q*.json
    reports/parts/<topic-folder>/<saved-graph-image>

Each question JSON should contain:
    {
        "qid": "q1",
        "question": "Question text",
        "summary": "Summary text",
        "images": ["graph.png"]
    }

Output:
    README.md
"""

import json
import re
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = ROOT_DIR / "notebook"
TABLES_DIR = ROOT_DIR / "data" / "tables"
PARTS_DIR = ROOT_DIR / "reports" / "parts"
README_PATH = ROOT_DIR / "README.md"

PROJECT_NAME = "Climate, Emissions and Air Quality Analysis"

DESCRIPTION = (
    "A data analysis project exploring atmospheric CO2 and greenhouse-gas trends, "
    "country-level emissions, relationships between emissions and temperature, "
    "climate-policy events, air pollution, and data quality. The project uses "
    "Jupyter notebooks to analyse data and produces graphs and written findings."
)


def markdown_escape(value):
    """Escape HTML-sensitive characters for safe Markdown text."""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_notebook(path):
    """Return (title, questions) from notebook Markdown cells."""
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: Could not read {path.name}: {exc}")
        return path.stem.replace("_", " ").title(), []

    title = path.stem.replace("_", " ").title()
    questions = []

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue

        source = cell.get("source", "")
        text = "".join(source) if isinstance(source, list) else source
        text = text.strip()

        if text.startswith("# ") and title == path.stem.replace("_", " ").title():
            title = text[2:].splitlines()[0].strip()

        match = re.match(r"###\s+(Q\d+)\.\s*(.+)", text)
        if match:
            questions.append((match.group(1), match.group(2).strip()))

    return title, questions


def notebooks_section():
    files = sorted(NOTEBOOK_DIR.glob("*.ipynb")) if NOTEBOOK_DIR.exists() else []
    if not files:
        return "_No notebooks found in `notebook/`._\n"

    lines = [
        "| Notebook | Topic | Questions |",
        "|---|---|---:|",
    ]

    for path in files:
        title, questions = read_notebook(path)
        lines.append(
            f"| `{path.name}` | {markdown_escape(title)} | "
            f"{len(questions) if questions else '-'} |"
        )

    return "\n".join(lines) + "\n"


def tables_section():
    files = sorted(TABLES_DIR.glob("*.csv")) if TABLES_DIR.exists() else []
    if not files:
        return "_CSV tables have not been generated yet. Run the data preparation notebook._\n"

    return "\n".join(
        f"- `{path.relative_to(ROOT_DIR).as_posix()}`" for path in files
    ) + "\n"


def read_question_record(path):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: Skipping unreadable report file {path}: {exc}")
        return None

    if not isinstance(record, dict):
        return None

    return record


def question_sort_key(path):
    match = re.search(r"q(\d+)", path.stem, re.IGNORECASE)
    return (int(match.group(1)) if match else 0, path.name.lower())


def topic_title(topic_dir):
    """Use notebook title where possible, otherwise format the topic folder."""
    slug = topic_dir.name.split("_", 1)[-1]
    notebook_candidates = sorted(NOTEBOOK_DIR.glob(f"*{slug}*.ipynb")) if NOTEBOOK_DIR.exists() else []

    for notebook_path in notebook_candidates:
        title, _ = read_notebook(notebook_path)
        if title:
            return title

    return re.sub(r"[_-]+", " ", slug).strip().title()


def image_markdown(image_path):
    """Return a relative Markdown image reference, suitable for GitHub README."""
    relative = image_path.relative_to(ROOT_DIR).as_posix()
    return f"![{markdown_escape(image_path.stem)}]({relative})"


def project_report_section():
    """
    Embed each saved topic and question in this order:
    topic -> question -> graph image(s) -> summary.
    """
    topic_dirs = sorted(path for path in PARTS_DIR.iterdir() if path.is_dir()) if PARTS_DIR.exists() else []

    if not topic_dirs:
        return (
            "_No saved report sections found in `reports/parts/`. "
            "Run the analysis notebooks first to generate question JSON files and graphs._\n"
        )

    output = []
    total_questions = 0

    for topic_dir in topic_dirs:
        records = sorted(topic_dir.glob("q*.json"), key=question_sort_key)
        if not records:
            continue

        output.append(f"## {markdown_escape(topic_title(topic_dir))}")
        output.append("")

        for record_path in records:
            record = read_question_record(record_path)
            if record is None:
                continue

            qid = str(record.get("qid", record_path.stem)).upper()
            question = str(record.get("question", "Question text unavailable.")).strip()
            summary = str(record.get("summary", "")).strip()
            image_names = record.get("images", [])
            if not isinstance(image_names, list):
                image_names = []

            output.extend([
                f"### {markdown_escape(qid)}. {markdown_escape(question)}",
                "",
            ])

            existing_images = []
            for name in image_names:
                image_path = topic_dir / str(name)
                if image_path.exists() and image_path.is_file():
                    existing_images.append(image_path)

            if existing_images:
                for image_path in existing_images:
                    output.extend([image_markdown(image_path), ""])
            else:
                output.extend(["_Graph image not found in the saved report outputs._", ""])

            output.extend(["**Summary**", ""])

            if summary:
                paragraphs = re.split(r"\n\s*\n", summary)
                for paragraph in paragraphs:
                    paragraph = " ".join(paragraph.split())
                    if paragraph:
                        output.extend([markdown_escape(paragraph), ""])
            else:
                output.extend(["_No summary was saved for this question._", ""])

            output.extend(["---", ""])
            total_questions += 1

    if total_questions == 0:
        return (
            "_No saved question records were found. Expected files such as "
            "`reports/parts/<topic-folder>/q1.json`._\n"
        )

    output.insert(0, f"_Report generated from {total_questions} saved analysis questions._")
    output.insert(1, "")
    return "\n".join(output).rstrip() + "\n"


def build():
    notebooks = notebooks_section()
    tables = tables_section()
    report = project_report_section()

    return f"""# {PROJECT_NAME}

{DESCRIPTION}

## Project goals

- Analyse long-term atmospheric CO2 and greenhouse-gas trends.
- Compare emissions across countries.
- Investigate relationships between emissions and temperature anomalies.
- Explore changes surrounding major climate policies and historical events.
- Analyse air pollution, including PM2.5 where data is available.
- Evaluate data quality, coverage, assumptions, and limitations.
- Communicate results with graphs and evidence-based summaries.

## How to run

### 1. Install dependencies

Use Python 3.10 or later.

```bash
pip install pandas numpy scipy plotly kaleido reportlab pillow nbformat nbclient ipykernel
```

Kaleido 1.x may require Chrome for graph export. If needed, run:

```bash
plotly_get_chrome
```

### 2. Prepare the data

Open `notebook/00_setup_data.ipynb` and run its cells in order to download/load,
clean, and prepare the source data and CSV tables.

### 3. Run the analysis

Run notebooks `01` through `07` in the `notebook/` directory. Each notebook
should analyse its questions, create graphs, print summaries, and save report
outputs under `reports/parts/`.

### 4. Generate the PDF report (optional)

Build the PDF using outputs already saved by the notebooks:

```bash
python src/make_pdf.py
```

Execute notebooks `01` through `07` first, then build the PDF:

```bash
python src/make_pdf.py --run
```

The PDF output is `reports/Climate_Emissions_Report.pdf`.

### 5. Generate this README

From the project root, run:

```bash
python src/make_readme.py
```

This updates `README.md`, including the project report below. Rerun it after
updating notebook outputs so the embedded report stays current.

## Notebooks

{notebooks}

## Data tables

{tables}

# Project Report

The following report is embedded directly in this README. For every topic, it
lists each saved analysis question, its graph image, and its written summary.

{report}

## Interpretation notes

- Correlation does not by itself establish causation.
- Before-and-after policy comparisons can show associations but do not prove that a policy caused the observed change.
- Temperature anomalies depend on the baseline period; state the baseline when quoting values.
- Check units, missing values, geographic coverage, time coverage, and source definitions before comparing datasets.

---

_Generated by `src/make_readme.py` on {date.today():%d %B %Y}._
"""


def main():
    README_PATH.write_text(build(), encoding="utf-8")
    print(f"README created: {README_PATH}")


if __name__ == "__main__":
    main()
