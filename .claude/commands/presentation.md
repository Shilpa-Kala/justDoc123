# Presentation Generator Agent Skill

You are an expert business presentation creator. When invoked, follow these steps precisely to produce a polished, business-level PowerPoint file.

---

## Step 1 — Read the Input

The user will supply content in one of these forms:
- A **file path** (e.g., `report.txt`, `data.md`, `notes.pdf`)
- **Raw text** pasted directly into the prompt
- A **URL** to fetch content from

**Actions:**
1. If a file path is given, read the file with the Read tool.
2. If a URL is given, fetch it with the WebFetch tool.
3. If raw text is given, use it as-is.
4. Confirm the content was loaded, then proceed.

---

## Step 2 — Generate a Consolidated Summary & Slide Plan

Analyze the content and produce a structured JSON slide plan. Use this exact schema:

```json
{
  "title": "Presentation Title",
  "subtitle": "Subtitle or date or author",
  "theme": "corporate|technology|healthcare|finance|general",
  "slides": [
    {
      "type": "title",
      "title": "...",
      "subtitle": "..."
    },
    {
      "type": "agenda",
      "title": "Agenda",
      "items": ["Topic 1", "Topic 2", "Topic 3"]
    },
    {
      "type": "content",
      "title": "Slide Title",
      "bullets": ["Key point 1", "Key point 2", "Key point 3"],
      "speaker_notes": "Expanded context for the presenter..."
    },
    {
      "type": "diagram",
      "title": "Diagram Title",
      "diagram_type": "flowchart|process|comparison|timeline|pie|bar|org_chart",
      "description": "What this diagram shows",
      "data": {}
    },
    {
      "type": "stats",
      "title": "Key Metrics",
      "stats": [
        {"label": "Metric Name", "value": "42%", "description": "Brief context"}
      ]
    },
    {
      "type": "quote",
      "title": "Key Insight",
      "quote": "...",
      "attribution": "Source or author"
    },
    {
      "type": "summary",
      "title": "Key Takeaways",
      "bullets": ["Takeaway 1", "Takeaway 2", "Takeaway 3"]
    },
    {
      "type": "closing",
      "title": "Thank You",
      "subtitle": "Questions & Discussion",
      "contact": "contact@company.com"
    }
  ]
}
```

**Slide planning rules:**
- Always start with a `title` slide and end with a `closing` slide.
- Include an `agenda` slide as the second slide.
- Add a `summary` slide near the end.
- Aim for **8–15 slides** total — concise, executive-level content.
- Bullets should be **punchy, 10 words max** each.
- Include a `diagram` slide whenever the content has: processes, comparisons, timelines, hierarchies, metrics, or flows.
- Include a `stats` slide when there are 3+ quantitative data points.
- Include a `quote` slide for compelling insights or executive quotes.

---

## Step 3 — Determine and Plan Diagrams

For each `diagram` slide in the plan, populate the `data` field according to `diagram_type`:

**flowchart / process:**
```json
{"steps": ["Step 1", "Step 2", "Step 3", "Step 4"]}
```

**comparison:**
```json
{
  "labels": ["Option A", "Option B"],
  "criteria": ["Cost", "Speed", "Quality", "Risk"],
  "values": [[4, 2, 5, 3], [2, 5, 3, 4]]
}
```

**timeline:**
```json
{
  "events": [
    {"date": "Q1 2024", "event": "Project Kickoff"},
    {"date": "Q2 2024", "event": "Phase 1 Complete"}
  ]
}
```

**pie:**
```json
{"labels": ["Category A", "Category B", "Category C"], "values": [45, 35, 20]}
```

**bar:**
```json
{
  "categories": ["Q1", "Q2", "Q3", "Q4"],
  "series": [{"name": "Revenue", "values": [120, 145, 162, 198]}]
}
```

**org_chart:**
```json
{
  "root": "CEO",
  "children": [
    {"name": "CTO", "children": ["Engineering", "Product"]},
    {"name": "CFO", "children": ["Finance", "Legal"]}
  ]
}
```

---

## Step 4 — Generate the PowerPoint File

Save the slide plan as `slides_plan.json` in the current directory, then run the generation script:

```bash
# Install dependencies if needed
pip install python-pptx matplotlib pillow requests -q

# Run the generator
python3 scripts/generate_presentation.py slides_plan.json
```

The script will output: `<presentation_title>.pptx`

---

## Step 5 — Confirm and Report

After the script completes:
1. Confirm the `.pptx` file was created.
2. Report:
   - File name and location
   - Number of slides generated
   - Diagrams included (types and titles)
   - Theme applied
3. Offer to refine any slides or regenerate with different content.

---

## Quality Standards

- All slides use a **professional corporate visual theme** with consistent colors, fonts, and spacing.
- Diagrams are **auto-generated as embedded images** — no placeholders.
- Speaker notes provide **presenter context** for every content slide.
- The deck is **ready to present** — no manual editing required.
