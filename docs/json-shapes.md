SCRUM-292: JSON column shapes (PROPOSED, needs AI team confirmation)

The ERD has jsonb columns whose inner keys are not enforced by the database.
Below are the keys we guessed. AI teammates, please confirm or change them
before anyone codes against them.

1) messages.citations
A list. One item per source used in the answer.
Based on the citation fields in the tech stack doc (section 5, item 9).

[
  {
    "source_id": "uuid of the row in legal_chunks",
    "source_type": "legislation | case",
    "title": "name of the law or case",
    "reference": "article number or case number",
    "passage": "the quoted text used",
    "url": "link to the source"
  }
]

Note: the tech stack doc says source_type is "legislation or case", while
legal_chunks.source_type in the ERD uses "law | ruling". We should pick one
set of values.

2) workflows.state
Different for each agent (workflows.kind). Guessed examples:

case_prep (PRD L8):
{
  "current_step": 3,
  "issues_found": [],
  "missing_facts": [],
  "sources_used": []
}

intake (PRD C5):
{
  "niche": null,
  "fields_filled": [],
  "fields_missing": []
}

scheduling (PRD C10):
{
  "proposed_slots": [],
  "chosen_slot": null
}

3) requests.summary and cases.summary
Built by the intake agent (PRD C5). Unknown fields must be "not provided",
never invented.

{
  "niche": "labor",
  "facts": "",
  "dates": [],
  "parties": [{ "name": "", "role": "" }],
  "urgency": "",
  "budget": "",
  "preferred_times": [],
  "cited_articles": []
}

4) audit_events.before / after
The old and new values of what changed (PRD L9).
Example: before {"urgency": "low"}, after {"urgency": "high"}

5) documents.content
Depends on documents.type: contract_review, case_prep, saved_research.
Keys not decided yet. The owner of each feature should define them.

QUESTIONS FOR THE TEAM
- Are these keys enough for your part? What should be added or renamed?
- Which source_type values do we use: "legislation | case" or "law | ruling"?
- Where do we store the agreed shapes? Suggestion: docs/json-shapes.md