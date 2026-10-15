"""
report.py - tiny helper used by every analysis notebook.

Each question cell calls:
    save_report(TOPIC, "q1", "The question text", fig, summary_text)

That writes (under <project>/reports/parts/<NN>_<topic>/):
    q1_1.png   the graph(s)      (needs:  pip install -U kaleido)
    q1.json    question + summary + image names

src/make_pdf.py then collects everything into one PDF.
"""
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PARTS_DIR = ROOT_DIR / "reports" / "parts"

# topic slug -> (order in the PDF, title shown in the PDF)
TOPICS = {
    "global_trends":          (1, "Global Trends"),
    "gases_warming":          (2, "Which Gases Contribute to Warming"),
    "countries_emissions":    (3, "Countries and Emissions"),
    "emissions_temperature":  (4, "Emissions and Temperature"),
    "policy_events":          (5, "Policy Events and Emissions"),
    "air_pollution":          (6, "Air Pollution"),
    "data_quality":           (7, "Data Quality as a Finding"),
}


def topic_dir(topic):
    order, _ = TOPICS[topic]
    return PARTS_DIR / f"{order:02d}_{topic}"


def save_report(topic, qid, question, figs, summary, scale=2):
    """Save the figure(s) as PNG and the summary text as JSON for the PDF."""
    out = topic_dir(topic)
    out.mkdir(parents=True, exist_ok=True)

    if not isinstance(figs, (list, tuple)):
        figs = [figs]

    images = []
    for i, fig in enumerate(figs, start=1):
        path = out / f"{qid}_{i}.png"
        fig.write_image(
            str(path),
            width=fig.layout.width or 1000,
            height=fig.layout.height or 500,
            scale=scale,
        )
        images.append(path.name)

    record = {
        "topic": topic,
        "qid": qid,
        "question": question,
        "images": images,
        "summary": " ".join(str(summary).split()) if "\n\n" not in str(summary)
        else str(summary).strip(),
    }
    (out / f"{qid}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[report] saved {topic}/{qid} ({len(images)} graph(s))")
