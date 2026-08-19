#!/usr/bin/env python3
"""
Course Recommendation Agent
----------------------------
Input : a student profile (background, goal, known_skills)
Output: an ordered, explained learning path of courses from the catalogue

Design:
  1. DETERMINISTIC PLANNING (no LLM, no hallucination risk):
     - goal -> required skills          (data/goal_skill_map.json)
     - skill -> course that teaches it  (data/courses.json)
     - courses are ordered by walking prerequisites first (topological sort),
       and any skill the student already knows is skipped entirely.
  2. EXPLANATION LAYER (optional LLM):
     - If ANTHROPIC_API_KEY is set, each course gets a natural-language
       rationale written by Claude, grounded in the *actual* plan data
       (never asked to invent courses or skills).
     - If no key is set, a clear template-based rationale is used instead,
       so the agent is 100% runnable with zero API cost/setup.
"""

import os
import json
import argparse
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load_json(name):
    with open(DATA_DIR / name, "r") as f:
        return json.load(f)


def build_lookup(courses):
    """skill_name -> course dict that teaches it (first match wins)."""
    lookup = {}
    for course in courses:
        for skill in course["skills_taught"]:
            lookup.setdefault(skill, course)
    return lookup


def plan_path(profile, courses, goal_skill_map):
    """
    Returns an ordered list of course dicts (no duplicates), respecting
    prerequisite skills, and skipping anything the student already knows.
    """
    skill_to_course = build_lookup(courses)
    known = set(profile.get("known_skills", []))
    goal = profile["goal"].lower().strip()

    if goal not in goal_skill_map:
        raise ValueError(
            f"Unknown goal '{goal}'. Available goals: {list(goal_skill_map.keys())}"
        )

    target_skills = goal_skill_map[goal]

    ordered_courses = []
    visited_course_ids = set()

    def visit(skill):
        if skill in known:
            return
        course = skill_to_course.get(skill)
        if course is None:
            return  # no course teaches this skill in the catalogue
        if course["id"] in visited_course_ids:
            return
        # Recurse into this course's prerequisites first (DFS topological order)
        for prereq_skill in course["prerequisites"]:
            visit(prereq_skill)
        if course["id"] not in visited_course_ids:
            visited_course_ids.add(course["id"])
            ordered_courses.append(course)
            known.add(course["skills_taught"][0])  # student "gains" this skill

    for skill in target_skills:
        visit(skill)

    return ordered_courses


def template_reason(profile, course, step_num, already_known):
    prereqs_met = [s for s in course["prerequisites"] if s in already_known]
    reason = f"Step {step_num}: {course['name']} teaches '{course['skills_taught'][0]}', " \
              f"which is required for the goal of becoming a {profile['goal']}."
    if prereqs_met:
        reason += f" You're ready for it because you already have: {', '.join(prereqs_met)}."
    else:
        reason += " No prior skill from your profile was needed for this step."
    return reason


def llm_reason(profile, course, step_num, already_known, client, model="claude-sonnet-4-6"):
    prompt = f"""You are helping explain a learning path recommendation to a student.

Student background: {profile['background']}
Student goal: {profile['goal']}
Skills the student already has at this point in the path: {sorted(already_known)}

The next recommended course is:
- Name: {course['name']}
- Skill it teaches: {course['skills_taught'][0]}
- Description: {course['description']}
- Prerequisites: {course['prerequisites']}

In 1-2 sentences, explain to the student why THIS course is the right next step
right now. Be specific and encouraging. Do not invent facts not given above."""
    response = client.messages.create(
        model=model,
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return f"Step {step_num}: " + response.content[0].text.strip()


def recommend(profile, courses, goal_skill_map, use_llm=False):
    path = plan_path(profile, courses, goal_skill_map)
    known = set(profile.get("known_skills", []))

    client = None
    if use_llm:
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                print("[warning] ANTHROPIC_API_KEY not set — falling back to template reasoning.\n")
                use_llm = False
            else:
                client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            print("[warning] `anthropic` package not installed — falling back to template reasoning.\n")
            use_llm = False

    results = []
    for i, course in enumerate(path, start=1):
        if use_llm and client:
            try:
                reason = llm_reason(profile, course, i, known, client)
            except Exception as e:
                reason = template_reason(profile, course, i, known) + f" (LLM call failed: {e})"
        else:
            reason = template_reason(profile, course, i, known)

        known.add(course["skills_taught"][0])
        results.append({
            "step": i,
            "course_id": course["id"],
            "course_name": course["name"],
            "level": course["level"],
            "reason": reason,
        })
    return results


def run_profile(profile, courses, goal_skill_map, use_llm):
    print("=" * 70)
    print(f"Student: {profile['name']}  |  Goal: {profile['goal']}")
    print(f"Background: {profile['background']}")
    print(f"Known skills: {profile.get('known_skills') or 'None'}")
    print("-" * 70)
    path = recommend(profile, courses, goal_skill_map, use_llm=use_llm)
    for step in path:
        print(f"[{step['step']}] {step['course_name']} ({step['level']})")
        print(f"    -> {step['reason']}\n")
    return {"profile": profile["name"], "goal": profile["goal"], "path": path}


def main():
    parser = argparse.ArgumentParser(description="Course Recommendation Agent")
    parser.add_argument("--profile", type=str, default=None,
                         help="Path to a single profile JSON file. If omitted, runs all sample profiles.")
    parser.add_argument("--llm", action="store_true",
                         help="Use Claude to generate natural-language rationale (needs ANTHROPIC_API_KEY).")
    parser.add_argument("--out", type=str, default="output/recommendations.json",
                         help="Where to write the JSON output.")
    args = parser.parse_args()

    courses = load_json("courses.json")
    goal_skill_map = load_json("goal_skill_map.json")

    if args.profile:
        with open(args.profile, "r") as f:
            profiles = [json.load(f)]
    else:
        profiles = load_json("sample_profiles.json")

    all_results = []
    for profile in profiles:
        all_results.append(run_profile(profile, courses, goal_skill_map, args.llm))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Saved full results to {out_path}")


if __name__ == "__main__":
    main()
