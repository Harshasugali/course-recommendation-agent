# Course Recommendation Agent

**Category:** HR & Recruitment · **Difficulty:** Beginner
Takes a student profile (background, goal, known skills) and produces an
ordered, explained learning path from a course catalogue.

> "My agent takes a student profile (goal + known skills) and produces an
> ordered list of courses, each with a reason it was recommended at that
> point in the path."

---

## 1. How it works

The agent has two layers, kept deliberately separate:

1. **Deterministic planner** (`plan_path` in `agent.py`)
   No AI involved here — this is plain graph logic, so the path is always
   correct and reproducible:
   - `data/goal_skill_map.json` maps a career goal → the skills needed.
   - `data/courses.json` maps each skill → the course that teaches it,
     plus that course's own prerequisite skills.
   - Starting from the goal's required skills, the agent recursively visits
     prerequisites first (a depth-first topological walk), and skips any
     skill the student already has in `known_skills`.
   - Result: an ordered course list with no forward references — you never
     see a course before its prerequisites.

2. **Explanation layer** (`template_reason` / `llm_reason`)
   - **Default (no API key needed):** a template fills in *why* each course
     was picked, using only real data from the plan (goal, skill taught,
     which known skills made the student "ready").
   - **Optional `--llm` flag:** if `ANTHROPIC_API_KEY` is set, each step's
     explanation is instead written by Claude in more natural language —
     but it's given the exact plan data and told not to invent anything, so
     it can't hallucinate a course or skill that isn't in the catalogue.

This means the agent is **100% runnable with zero setup cost**, and gets a
nicer explanation layer if you choose to add an API key.

---

## 2. Setup

```bash
git clone <this-repo-url>
cd course-recommendation-agent
pip install -r requirements.txt   # only needed for --llm mode
```

To use the optional LLM explanation layer:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

If you skip this, the agent still runs fully — it just uses the built-in
template explanations instead of Claude.

---

## 3. Run it

Run all 4 sample profiles (template mode, no key needed):

```bash
python3 agent.py
```

Run with Claude-generated explanations:

```bash
python3 agent.py --llm
```

Run a single custom profile:

```bash
python3 agent.py --profile data/sample_profiles.json --llm
```

(For a single profile, put one `{...}` object, not a list, in your own
`my_profile.json` and pass `--profile my_profile.json`.)

Output is printed to the console **and** saved as JSON to
`output/recommendations.json`.

---

## 4. Sample input / output

**Input profile** (`data/sample_profiles.json`, entry 1):

```json
{
  "name": "Ananya",
  "background": "Second-year commerce student, comfortable with Excel",
  "goal": "data analyst",
  "known_skills": []
}
```

**Output** (from `output/recommendations.json`):

```json
{
  "profile": "Ananya",
  "goal": "data analyst",
  "path": [
    { "step": 1, "course_id": "PY101", "course_name": "Python Programming Fundamentals", "level": "Beginner", "reason": "Step 1: Python Programming Fundamentals teaches 'python', which is required for the goal of becoming a data analyst. No prior skill from your profile was needed for this step." },
    { "step": 2, "course_id": "STAT101", "course_name": "Statistics for Data Analysis", "level": "Beginner", "reason": "..." },
    { "step": 3, "course_id": "SQL101", "course_name": "SQL & Relational Databases", "level": "Beginner", "reason": "..." },
    { "step": 4, "course_id": "DA201", "course_name": "Data Analysis with Pandas", "level": "Intermediate", "reason": "Step 4: Data Analysis with Pandas teaches 'data_analysis', ... You're ready for it because you already have: python, statistics." }
  ]
}
```

Three more worked examples (Rahul → data scientist, Priya → full stack
developer, Karan → cloud engineer) are included in `data/sample_profiles.json`
and their full console transcript is reproduced in `sample_run_output.txt`.

---

## 5. Project structure

```
course-recommendation-agent/
├── agent.py                  # the agent (planner + explanation layer)
├── data/
│   ├── courses.json          # course catalogue (10 courses)
│   ├── goal_skill_map.json   # goal -> required skills
│   └── sample_profiles.json  # 4 sample students
├── output/
│   └── recommendations.json  # generated on each run
├── sample_run_output.txt     # saved console transcript
├── requirements.txt
└── README.md
```

---

## 6. Design tradeoffs & what I'd improve with more time

- **Rule-based planner over pure-LLM planning.** I chose a deterministic
  graph walk instead of asking an LLM to "plan the path" because course
  sequencing has a *correct* answer (don't recommend React before HTML/CSS),
  and an LLM can silently get that wrong or invent a course. The LLM is only
  used for the part that's genuinely subjective — explaining *why* — where a
  wrong word choice isn't a broken recommendation.
- **Small hand-written catalogue (10 courses, 6 goals).** For a 24-hour
  build this keeps the demo legible and testable end-to-end. With more time
  I'd load a larger catalogue from a CSV/DB and generalize `goal_skill_map`
  into fuzzy goal matching (e.g. embedding similarity) instead of exact
  string keys like `"data analyst"`.
  A user typing "Data Analyst" or "data analytics" currently needs an exact
  (case-insensitive) match against the map — that's the biggest usability
  gap right now.
- **One course per skill.** `build_lookup` takes the first course that
  teaches a skill. A real catalogue would have multiple courses per skill at
  different levels/providers, and the agent should pick based on the
  student's stated level, not just take the first match.
- **No persistence layer.** Each run is stateless — profiles are read from
  JSON, not stored. For a real product I'd add SQLite to track a student's
  progress over time and only recommend the *remaining* path.
- **LLM failure handling.** If the Claude call fails mid-run (rate limit,
  bad key), the agent falls back to the template reason for that step rather
  than crashing the whole run — I'd add retries with backoff next.
