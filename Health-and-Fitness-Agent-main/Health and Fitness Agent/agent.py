"""
APEX Fitness Agent - Groq API Version
Enhanced coaching tools with adaptive planning, nutrition analysis, safety checks,
progress logging support, and motivational guidance.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Exercise and nutrition knowledge base ---------------------------------

EXERCISE_DB = [
    {
        "name": "Bodyweight Squat",
        "muscle_group": "legs",
        "equipment": "minimal",
        "difficulty": "beginner",
        "description": "Hip and knee dominant squat pattern using bodyweight.",
        "form_tips": ["Keep chest tall", "Knees track over toes", "Brace core throughout"],
        "alternatives": ["Goblet Squat", "Leg Press"],
        "contraindications": ["acute_knee_pain"],
    },
    {
        "name": "Goblet Squat",
        "muscle_group": "legs",
        "equipment": "home",
        "difficulty": "beginner",
        "description": "Front-loaded squat with dumbbell or kettlebell.",
        "form_tips": ["Hold weight close to chest", "Sit between hips", "Control descent"],
        "alternatives": ["Bodyweight Squat", "Split Squat"],
        "contraindications": ["acute_knee_pain"],
    },
    {
        "name": "Romanian Deadlift",
        "muscle_group": "posterior_chain",
        "equipment": "gym",
        "difficulty": "intermediate",
        "description": "Hip hinge focusing on hamstrings and glutes.",
        "form_tips": ["Neutral spine", "Push hips back", "Keep bar close"],
        "alternatives": ["Dumbbell RDL", "Hip Thrust"],
        "contraindications": ["acute_low_back_pain"],
    },
    {
        "name": "Push-Up",
        "muscle_group": "chest",
        "equipment": "minimal",
        "difficulty": "beginner",
        "description": "Horizontal pressing using bodyweight.",
        "form_tips": ["Body in straight line", "Elbows 30-45 degrees", "Full range of motion"],
        "alternatives": ["Incline Push-Up", "Dumbbell Bench Press"],
        "contraindications": ["acute_shoulder_pain", "wrist_pain"],
    },
    {
        "name": "Dumbbell Bench Press",
        "muscle_group": "chest",
        "equipment": "home",
        "difficulty": "intermediate",
        "description": "Horizontal pressing with dumbbells.",
        "form_tips": ["Scapulae retracted", "Wrists stacked", "Control eccentric"],
        "alternatives": ["Push-Up", "Machine Chest Press"],
        "contraindications": ["acute_shoulder_pain"],
    },
    {
        "name": "Lat Pulldown",
        "muscle_group": "back",
        "equipment": "gym",
        "difficulty": "beginner",
        "description": "Vertical pulling for lats and upper back.",
        "form_tips": ["Lead with elbows", "Avoid leaning back excessively", "Pause at chest"],
        "alternatives": ["Band Pulldown", "Assisted Pull-Up"],
        "contraindications": ["acute_shoulder_pain"],
    },
    {
        "name": "Dumbbell Row",
        "muscle_group": "back",
        "equipment": "home",
        "difficulty": "beginner",
        "description": "Single-arm row for lats and mid-back.",
        "form_tips": ["Flat back", "Pull elbow to hip", "Avoid torso twist"],
        "alternatives": ["Cable Row", "Band Row"],
        "contraindications": ["acute_low_back_pain"],
    },
    {
        "name": "Overhead Press",
        "muscle_group": "shoulders",
        "equipment": "gym",
        "difficulty": "intermediate",
        "description": "Vertical pressing for deltoids and triceps.",
        "form_tips": ["Ribs down", "Glutes tight", "Press in straight path"],
        "alternatives": ["Landmine Press", "Seated Dumbbell Press"],
        "contraindications": ["acute_shoulder_pain", "neck_pain"],
    },
    {
        "name": "Plank",
        "muscle_group": "core",
        "equipment": "minimal",
        "difficulty": "beginner",
        "description": "Isometric trunk stability drill.",
        "form_tips": ["Neutral pelvis", "Elbows under shoulders", "Steady breathing"],
        "alternatives": ["Dead Bug", "Side Plank"],
        "contraindications": ["acute_low_back_pain"],
    },
    {
        "name": "Glute Bridge",
        "muscle_group": "glutes",
        "equipment": "minimal",
        "difficulty": "beginner",
        "description": "Hip extension pattern for glutes and posterior chain.",
        "form_tips": ["Drive through heels", "Rib cage down", "Pause at top"],
        "alternatives": ["Hip Thrust", "Cable Pull Through"],
        "contraindications": [],
    },
    {
        "name": "Cycling Intervals",
        "muscle_group": "conditioning",
        "equipment": "gym",
        "difficulty": "intermediate",
        "description": "Interval conditioning for aerobic and anaerobic fitness.",
        "form_tips": ["Maintain cadence", "Control breathing", "Progress volume gradually"],
        "alternatives": ["Rowing Intervals", "Brisk Walk Intervals"],
        "contraindications": ["acute_knee_pain"],
    },
    {
        "name": "Incline Walk",
        "muscle_group": "conditioning",
        "equipment": "minimal",
        "difficulty": "beginner",
        "description": "Low impact cardio option for calorie burn.",
        "form_tips": ["Upright torso", "Smooth foot strike", "Steady pace"],
        "alternatives": ["Cycling", "Elliptical"],
        "contraindications": [],
    },
]

FOOD_DB = {
    "chicken breast": {"protein": 31, "carbs": 0, "fat": 3.6, "calories": 165, "fiber": 0},
    "rice": {"protein": 2.7, "carbs": 28, "fat": 0.3, "calories": 130, "fiber": 0.4},
    "broccoli": {"protein": 2.8, "carbs": 7, "fat": 0.4, "calories": 34, "fiber": 2.6},
    "egg": {"protein": 6.3, "carbs": 0.6, "fat": 5.3, "calories": 78, "fiber": 0},
    "oats": {"protein": 13.2, "carbs": 67.7, "fat": 6.5, "calories": 389, "fiber": 10.1},
    "banana": {"protein": 1.3, "carbs": 22.8, "fat": 0.3, "calories": 89, "fiber": 2.6},
    "salmon": {"protein": 20, "carbs": 0, "fat": 13, "calories": 208, "fiber": 0},
    "tofu": {"protein": 8, "carbs": 2, "fat": 4.8, "calories": 76, "fiber": 0.3},
    "lentils": {"protein": 9, "carbs": 20, "fat": 0.4, "calories": 116, "fiber": 8},
    "greek yogurt": {"protein": 10, "carbs": 3.6, "fat": 0.4, "calories": 59, "fiber": 0},
    "almonds": {"protein": 21, "carbs": 22, "fat": 49, "calories": 579, "fiber": 12.5},
    "avocado": {"protein": 2, "carbs": 9, "fat": 15, "calories": 160, "fiber": 7},
    "sweet potato": {"protein": 1.6, "carbs": 20.1, "fat": 0.1, "calories": 86, "fiber": 3},
    "paneer": {"protein": 18.3, "carbs": 1.2, "fat": 20.8, "calories": 265, "fiber": 0},
    "chapati": {"protein": 3.1, "carbs": 18, "fat": 3, "calories": 120, "fiber": 2.7},
}

EQUIPMENT_MAP = {
    "none": "minimal",
    "minimal": "minimal",
    "home": "home",
    "gym": "gym",
    "specific_machines": "gym",
}


# ---- Utility helpers --------------------------------------------------------

def _normalise_goal(goal: str) -> str:
    g = (goal or "general_fitness").strip().lower().replace(" ", "_")
    aliases = {
        "fat_loss": "weight_loss",
        "lose_weight": "weight_loss",
        "gain_muscle": "muscle_gain",
        "strength": "muscle_gain",
        "conditioning": "endurance",
        "flexibility": "flexibility",
    }
    return aliases.get(g, g)


def _normalise_level(level: str) -> str:
    l = (level or "beginner").strip().lower()
    if l not in {"beginner", "intermediate", "advanced"}:
        return "beginner"
    return l


def _energy_multiplier(energy_level: str, soreness_level: str) -> float:
    energy_map = {
        "very_low": 0.75,
        "low": 0.85,
        "normal": 1.0,
        "high": 1.08,
    }
    soreness_map = {
        "none": 1.0,
        "mild": 0.95,
        "moderate": 0.88,
        "high": 0.75,
    }
    return energy_map.get((energy_level or "normal").lower(), 1.0) * soreness_map.get(
        (soreness_level or "none").lower(), 1.0
    )


def _match_equipment(exercise_equipment: str, available_equipment: str) -> bool:
    if available_equipment == "gym":
        return True
    if available_equipment == "home":
        return exercise_equipment in {"minimal", "home"}
    return exercise_equipment == "minimal"


def _contraindicated(exercise: dict[str, Any], limitations: list[str]) -> bool:
    limit_set = {str(item).strip().lower().replace(" ", "_") for item in limitations}
    blocked = {str(item).strip().lower() for item in exercise.get("contraindications", [])}
    return bool(limit_set.intersection(blocked))


def _pick_exercises(
    targets: list[str],
    equipment: str,
    level: str,
    limitations: list[str],
    amount: int = 5,
) -> list[dict[str, Any]]:
    allowed = []
    for ex in EXERCISE_DB:
        if ex["muscle_group"] not in targets:
            continue
        if not _match_equipment(ex["equipment"], equipment):
            continue
        if _contraindicated(ex, limitations):
            continue
        if level == "beginner" and ex["difficulty"] == "advanced":
            continue
        allowed.append(ex)

    if not allowed:
        # Safe fallback to bodyweight-friendly work.
        allowed = [
            ex
            for ex in EXERCISE_DB
            if ex["equipment"] == "minimal" and not _contraindicated(ex, limitations)
        ]
    return allowed[:amount]


def _exercise_volume(level: str, duration_min: int, intensity_factor: float) -> dict[str, Any]:
    base_sets = {"beginner": 2, "intermediate": 3, "advanced": 4}.get(level, 2)
    base_reps = {
        "beginner": "10-12",
        "intermediate": "8-12",
        "advanced": "6-10",
    }.get(level, "10-12")

    if duration_min <= 20:
        sets = max(2, base_sets - 1)
        rest = "45-60s"
    elif duration_min <= 40:
        sets = base_sets
        rest = "60-75s"
    else:
        sets = min(5, base_sets + 1)
        rest = "75-120s"

    if intensity_factor < 0.82:
        rest = "75-120s"
    return {"sets": sets, "reps": base_reps, "rest": rest}


def _parse_meal_text(meal_description: str) -> tuple[list[str], list[str]]:
    parts = [
        p.strip().lower()
        for p in re.split(r",|\+| and | with |\n", meal_description or "")
        if p.strip()
    ]
    matched, unmatched = [], []
    for p in parts:
        found = None
        for food in FOOD_DB:
            if food in p:
                found = food
                break
        if found:
            matched.append(found)
        else:
            unmatched.append(p)
    return matched, unmatched


def _cal_from_macros(p: float, c: float, f: float) -> float:
    return (p * 4) + (c * 4) + (f * 9)


# ---- Tool functions ---------------------------------------------------------

def calculate_bmi(weight_kg: float, height_cm: float) -> dict[str, Any]:
    h = height_cm / 100
    bmi = round(weight_kg / (h**2), 1)
    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal weight"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"
    return {"bmi": bmi, "category": category, "healthy_range": "18.5-24.9"}


def calculate_tdee(weight_kg: float, height_cm: float, age: int, gender: str, activity_level: str) -> dict[str, Any]:
    g = (gender or "").lower().strip()
    if g == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    mult = multipliers.get((activity_level or "moderate").lower().replace(" ", "_"), 1.55)
    tdee = round(bmr * mult)
    return {
        "bmr": round(bmr),
        "tdee": tdee,
        "weight_loss": max(1200, tdee - 500),
        "weight_gain": tdee + 250,
        "maintenance": tdee,
    }


def search_exercises(
    muscle_group: str = "",
    equipment: str = "",
    difficulty: str = "",
    query: str = "",
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    limitations = limitations or []
    mg = (muscle_group or "").strip().lower()
    eq = EQUIPMENT_MAP.get((equipment or "").strip().lower(), (equipment or "").strip().lower())
    diff = (difficulty or "").strip().lower()
    q = (query or "").strip().lower()

    results = []
    for ex in EXERCISE_DB:
        if mg and mg != ex["muscle_group"]:
            continue
        if eq and not _match_equipment(ex["equipment"], eq):
            continue
        if diff and diff != ex["difficulty"]:
            continue
        if q and q not in ex["name"].lower() and q not in ex["description"].lower():
            continue
        if _contraindicated(ex, limitations):
            continue
        results.append(
            {
                "name": ex["name"],
                "muscle_group": ex["muscle_group"],
                "difficulty": ex["difficulty"],
                "equipment": ex["equipment"],
                "description": ex["description"],
                "form_tips": ex["form_tips"],
                "alternatives": ex["alternatives"],
                "resources": [
                    "https://exrx.net/Lists/Directory",
                    "https://www.cdc.gov/physical-activity-basics/index.html",
                ],
            }
        )

    return {
        "count": len(results),
        "items": results[:10],
    }


def generate_workout_plan(
    goal: str,
    level: str,
    frequency_per_week: int,
    equipment: str,
    duration_min: int = 45,
    time_constraint: str = "",
    limitations: list[str] | None = None,
    energy_level: str = "normal",
    soreness_level: str = "none",
) -> dict[str, Any]:
    goal = _normalise_goal(goal)
    level = _normalise_level(level)
    limitations = limitations or []

    equipment = EQUIPMENT_MAP.get((equipment or "minimal").lower(), "minimal")
    frequency_per_week = min(7, max(2, int(frequency_per_week or 3)))
    duration_min = int(duration_min or 45)
    if time_constraint:
        txt = time_constraint.lower().strip()
        if "15" in txt:
            duration_min = 15
        elif "30" in txt:
            duration_min = 30
        elif "60" in txt or "1 hour" in txt:
            duration_min = 60

    intensity_factor = _energy_multiplier(energy_level, soreness_level)
    volume = _exercise_volume(level, duration_min, intensity_factor)

    if goal in {"weight_loss", "endurance"}:
        day_focus = ["conditioning", "legs", "back", "chest", "core", "conditioning"]
    elif goal == "muscle_gain":
        day_focus = ["chest", "back", "legs", "shoulders", "posterior_chain", "core"]
    elif goal == "flexibility":
        day_focus = ["core", "glutes", "conditioning", "back", "core", "conditioning"]
    else:
        day_focus = ["legs", "chest", "back", "conditioning", "core", "glutes"]

    sessions = []
    for idx in range(frequency_per_week):
        focus = day_focus[idx % len(day_focus)]
        selected = _pick_exercises(
            targets=[focus, "core"] if focus != "core" else ["core", "glutes"],
            equipment=equipment,
            level=level,
            limitations=limitations,
            amount=4 if duration_min < 30 else 5,
        )

        main_work = []
        for ex in selected:
            main_work.append(
                {
                    "exercise": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": volume["sets"],
                    "reps": volume["reps"],
                    "rest": volume["rest"],
                    "form_tips": ex["form_tips"][:2],
                    "alternatives": ex["alternatives"][:2],
                }
            )

        sessions.append(
            {
                "day": f"Day {idx + 1}",
                "focus": focus,
                "warmup": [
                    "3-5 min light cardio",
                    "Dynamic mobility for hips/shoulders",
                    "1 lighter set before first lift",
                ],
                "main_work": main_work,
                "cooldown": [
                    "2-5 min easy walk/breathing",
                    "Gentle stretches for worked muscles",
                ],
                "injury_prevention": [
                    "Stop any movement causing sharp pain",
                    "Use controlled tempo and full range only if pain-free",
                ],
            }
        )

    recovery_days = max(0, 7 - frequency_per_week)
    progressive_overload = [
        "Add 1-2 reps per set when all sets feel <= RPE 7",
        "Increase load by 2.5-5% once rep targets are met for two sessions",
        "Deload every 4-6 weeks by reducing volume by about 30%",
    ]

    adaptive_note = "Normal intensity session."
    if intensity_factor < 0.85:
        adaptive_note = "Reduced intensity recommended today due to low energy or soreness."
    elif intensity_factor > 1.05:
        adaptive_note = "Higher energy detected - optional top set or short finisher can be added."

    return {
        "summary": {
            "goal": goal,
            "level": level,
            "equipment": equipment,
            "frequency_per_week": frequency_per_week,
            "duration_min": duration_min,
            "recovery_days": recovery_days,
        },
        "adaptive_recommendation": adaptive_note,
        "weekly_plan": sessions,
        "progressive_overload": progressive_overload,
        "equipment_substitution_rule": "If a movement is unavailable, use alternatives from the same muscle group and movement pattern.",
        "safety_disclaimer": "This is educational fitness guidance, not medical care. Consult a qualified professional for injuries or medical conditions.",
    }


def analyze_nutrition(meal_description: str, calorie_target: int = 0) -> dict[str, Any]:
    matched, unmatched = _parse_meal_text(meal_description)

    protein = carbs = fat = calories = fiber = 0.0
    item_breakdown = []
    for item in matched:
        macros = FOOD_DB[item]
        protein += macros["protein"]
        carbs += macros["carbs"]
        fat += macros["fat"]
        fiber += macros.get("fiber", 0)
        calories += macros["calories"]
        item_breakdown.append({"food": item, **macros})

    # If we matched very little, estimate from macro conversion fallback.
    if matched and calories <= 0:
        calories = _cal_from_macros(protein, carbs, fat)

    target_gap = None
    if calorie_target > 0:
        target_gap = round(calorie_target - calories)

    suggestions = []
    if protein < 25:
        suggestions.append("Protein is low. Add lean protein like chicken, tofu, lentils, eggs, or Greek yogurt.")
    if fiber < 8:
        suggestions.append("Fiber is low. Add vegetables, fruit, legumes, or whole grains.")
    if calorie_target > 0 and target_gap is not None:
        if target_gap > 200:
            suggestions.append("Meal is below target. Add a nutrient-dense side or snack.")
        elif target_gap < -200:
            suggestions.append("Meal is above target. Reduce added fats or portion size.")

    hydration_ml = 2200
    if calories > 700:
        hydration_ml = 2800

    return {
        "meal_input": meal_description,
        "recognized_items": item_breakdown,
        "unmatched_items": unmatched[:8],
        "totals": {
            "protein_g": round(protein, 1),
            "carbs_g": round(carbs, 1),
            "fat_g": round(fat, 1),
            "fiber_g": round(fiber, 1),
            "calories": round(calories),
        },
        "target_comparison": {
            "calorie_target": calorie_target if calorie_target > 0 else None,
            "calorie_gap": target_gap,
        },
        "suggestions": suggestions,
        "hydration_recommendation": f"Aim for about {hydration_ml} ml water today, more if sweating heavily.",
    }


def generate_meal_plan(
    calories_target: int,
    goal: str,
    diet_type: str,
    cuisine_preference: str = "mixed",
    budget: str = "medium",
    meals_per_day: int = 3,
    allergies: list[str] | None = None,
) -> dict[str, Any]:
    allergies = {a.strip().lower() for a in (allergies or [])}
    goal = _normalise_goal(goal)
    diet = (diet_type or "standard").lower()

    macro_splits = {
        "weight_loss": {"protein": 0.35, "carbs": 0.35, "fat": 0.30},
        "muscle_gain": {"protein": 0.30, "carbs": 0.45, "fat": 0.25},
        "maintenance": {"protein": 0.27, "carbs": 0.43, "fat": 0.30},
        "endurance": {"protein": 0.22, "carbs": 0.53, "fat": 0.25},
    }
    split = macro_splits.get(goal, macro_splits["maintenance"])

    meal_templates = {
        "standard": [
            "Breakfast: Greek yogurt + oats + banana",
            "Lunch: Chicken breast + rice + broccoli",
            "Snack: Almonds + fruit",
            "Dinner: Salmon + sweet potato + salad",
        ],
        "vegetarian": [
            "Breakfast: Oats + milk + banana",
            "Lunch: Lentil bowl + rice + vegetables",
            "Snack: Greek yogurt + nuts",
            "Dinner: Paneer + chapati + mixed veggies",
        ],
        "vegan": [
            "Breakfast: Overnight oats + chia + fruit",
            "Lunch: Tofu stir-fry + rice",
            "Snack: Roasted chickpeas + fruit",
            "Dinner: Lentil curry + whole-grain roti",
        ],
        "keto": [
            "Breakfast: Eggs + avocado",
            "Lunch: Paneer/tofu salad with olive oil",
            "Snack: Nuts + seeds",
            "Dinner: Salmon + sauteed vegetables",
        ],
        "gluten-free": [
            "Breakfast: Eggs + fruit + yogurt",
            "Lunch: Chicken + quinoa + veggies",
            "Snack: Nuts + smoothie",
            "Dinner: Fish + potatoes + salad",
        ],
    }

    chosen = meal_templates.get(diet, meal_templates["standard"])

    filtered = []
    for meal in chosen:
        lowered = meal.lower()
        if any(a in lowered for a in allergies):
            continue
        filtered.append(meal)

    if not filtered:
        filtered = ["Allergy-safe custom meal needed. Ask user for ingredient-safe substitutions."]

    budget_note = {
        "low": "Focus on staples: oats, rice, lentils, eggs/tofu, seasonal produce.",
        "medium": "Mix staples with lean proteins and frozen vegetables for convenience.",
        "high": "Add variety with premium proteins, berries, and quality fats.",
    }.get((budget or "medium").lower(), "Use balanced whole-food choices.")

    return {
        "goal": goal,
        "diet_type": diet,
        "cuisine_preference": cuisine_preference,
        "budget": budget,
        "meals_per_day": meals_per_day,
        "calories": calories_target,
        "protein_g": round(calories_target * split["protein"] / 4),
        "carbs_g": round(calories_target * split["carbs"] / 4),
        "fat_g": round(calories_target * split["fat"] / 9),
        "daily_suggestions": filtered[: max(1, meals_per_day)],
        "weekly_rotation_tip": "Rotate protein source and vegetables every 2-3 days for adherence.",
        "hydration": "Baseline: 35 ml x bodyweight (kg). Add 500-1000 ml on training days.",
        "budget_note": budget_note,
    }


def calculate_calories_burned(activity: str, duration_min: int, weight_kg: float, intensity: str) -> dict[str, Any]:
    met_table = {
        "running": {"low": 7.0, "moderate": 9.8, "high": 12.8},
        "cycling": {"low": 5.5, "moderate": 8.0, "high": 11.0},
        "swimming": {"low": 5.8, "moderate": 7.0, "high": 10.0},
        "weightlifting": {"low": 3.0, "moderate": 5.0, "high": 6.0},
        "walking": {"low": 2.8, "moderate": 3.8, "high": 5.0},
        "yoga": {"low": 2.5, "moderate": 3.3, "high": 4.0},
        "hiit": {"low": 7.0, "moderate": 9.0, "high": 12.0},
        "rowing": {"low": 5.5, "moderate": 7.0, "high": 10.5},
    }
    act = (activity or "weightlifting").lower()
    key = next((k for k in met_table if k in act), "weightlifting")
    met = met_table[key].get((intensity or "moderate").lower(), 5.0)
    calories = round(met * weight_kg * (duration_min / 60))
    return {
        "activity": activity,
        "duration_min": duration_min,
        "weight_kg": weight_kg,
        "intensity": intensity,
        "calories_burned": calories,
        "met_value": met,
    }


def get_recovery_protocol(injury_type: str, severity: str = "mild") -> dict[str, Any]:
    injury = (injury_type or "general_soreness").strip().lower().replace(" ", "_")
    severity = (severity or "mild").strip().lower()

    protocols = {
        "knee_pain": {
            "safe_exercises": ["Glute Bridge", "Hip Hinge Drill", "Cycling (low resistance)"],
            "avoid": ["Deep knee flexion under load", "Plyometrics", "Running hills"],
        },
        "shoulder_pain": {
            "safe_exercises": ["Band Row", "Scapular Retraction", "Landmine Press (pain-free)"],
            "avoid": ["Heavy overhead press", "Dips", "Behind-neck movements"],
        },
        "low_back_pain": {
            "safe_exercises": ["Dead Bug", "Bird Dog", "Short walk"],
            "avoid": ["Loaded spinal flexion", "Heavy deadlifts", "Jerky twisting"],
        },
        "general_soreness": {
            "safe_exercises": ["Easy walk", "Light mobility", "Gentle stretching"],
            "avoid": ["Max effort lifting", "All-out intervals"],
        },
    }

    base = protocols.get(injury, protocols["general_soreness"])
    timeline = {
        "mild": "24-72 hours of reduced intensity and gradual return.",
        "moderate": "3-7 days with pain-free movement and progressive loading.",
        "severe": "Stop training that area and seek medical evaluation urgently.",
    }.get(severity, "24-72 hours with reduced intensity.")

    escalation = severity == "severe" or injury in {"chest_pain", "dizziness", "acute_injury"}

    return {
        "injury_type": injury,
        "severity": severity,
        "safe_exercises": base["safe_exercises"],
        "avoid": base["avoid"],
        "recovery_timeline": timeline,
        "when_to_escalate": "If pain is sharp, worsening, neurological, or persists beyond 7 days.",
        "seek_professional_care": escalation,
        "disclaimer": "I am an AI assistant, not a doctor. Consult a healthcare professional for diagnosis and treatment.",
    }


def get_motivation_message(
    goal: str,
    consistency_score: int = 0,
    communication_style: str = "balanced",
    milestone: str = "",
) -> dict[str, Any]:
    style = (communication_style or "balanced").lower()
    score = max(0, min(100, int(consistency_score or 0)))
    goal_text = (goal or "your fitness goal").replace("_", " ")

    if score >= 85:
        base = "You are building elite consistency. Keep the streak alive and protect your recovery."
    elif score >= 60:
        base = "Solid momentum. One focused session at a time will compound into big results."
    else:
        base = "Fresh restart mindset. Tiny wins this week can quickly rebuild confidence and routine."

    if style == "casual":
        msg = f"You are doing better than you think. Stay locked in on {goal_text} and stack one good day at a time."
    elif style == "formal":
        msg = f"Your current trajectory toward {goal_text} is promising. Maintain adherence and progressive effort."
    elif style == "high_motivation":
        msg = f"No excuses today. Execute the plan, protect your habits, and make {goal_text} inevitable."
    else:
        msg = base

    challenge = "Complete 3 sessions this week and log each one immediately after training."
    if score >= 85:
        challenge = "Add one technique-focused session and one recovery protocol session this week."

    return {
        "message": msg,
        "milestone": milestone or "Keep pushing forward.",
        "challenge": challenge,
    }


def create_smart_goal(
    goal_statement: str,
    timeframe_weeks: int,
    current_value: float,
    target_value: float,
    metric: str = "weight_kg",
) -> dict[str, Any]:
    weeks = max(1, int(timeframe_weeks or 1))
    delta = target_value - current_value
    weekly_required = round(delta / weeks, 3)

    achievability = "reasonable"
    if metric == "weight_kg" and abs(weekly_required) > 1.0:
        achievability = "aggressive"

    return {
        "specific": goal_statement,
        "measurable": f"Track {metric} weekly.",
        "achievable": achievability,
        "relevant": "Aligned with long-term health and fitness priorities.",
        "time_bound": f"{weeks} weeks",
        "current_value": current_value,
        "target_value": target_value,
        "weekly_change_needed": weekly_required,
        "milestones": [
            {
                "week": max(1, round(weeks * 0.25)),
                "target": round(current_value + weekly_required * max(1, round(weeks * 0.25)), 2),
            },
            {
                "week": max(2, round(weeks * 0.5)),
                "target": round(current_value + weekly_required * max(2, round(weeks * 0.5)), 2),
            },
            {
                "week": weeks,
                "target": target_value,
            },
        ],
    }


# ---- Groq tool definitions --------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_bmi",
            "description": "Calculate Body Mass Index (BMI) and weight category",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {"type": "number", "description": "Weight in kg"},
                    "height_cm": {"type": "number", "description": "Height in cm"},
                },
                "required": ["weight_kg", "height_cm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_tdee",
            "description": "Calculate Total Daily Energy Expenditure using Mifflin-St Jeor equation",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {"type": "number"},
                    "height_cm": {"type": "number"},
                    "age": {"type": "integer"},
                    "gender": {"type": "string", "enum": ["male", "female"]},
                    "activity_level": {
                        "type": "string",
                        "enum": ["sedentary", "light", "moderate", "active", "very_active"],
                    },
                },
                "required": ["weight_kg", "height_cm", "age", "gender", "activity_level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_workout_plan",
            "description": "Generate adaptive weekly workout plans with form tips, substitutions, and progression",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "enum": [
                            "weight_loss",
                            "muscle_gain",
                            "endurance",
                            "flexibility",
                            "general_fitness",
                        ],
                    },
                    "level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
                    "frequency_per_week": {"type": "integer", "minimum": 2, "maximum": 7},
                    "equipment": {
                        "type": "string",
                        "enum": ["none", "minimal", "home", "gym", "specific_machines"],
                    },
                    "duration_min": {"type": "integer", "minimum": 15, "maximum": 120},
                    "time_constraint": {"type": "string"},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                    "energy_level": {"type": "string", "enum": ["very_low", "low", "normal", "high"]},
                    "soreness_level": {"type": "string", "enum": ["none", "mild", "moderate", "high"]},
                },
                "required": ["goal", "level", "frequency_per_week", "equipment"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_meal_plan",
            "description": "Generate macro-balanced meal plans with diet restrictions and budget preferences",
            "parameters": {
                "type": "object",
                "properties": {
                    "calories_target": {"type": "integer"},
                    "goal": {"type": "string"},
                    "diet_type": {
                        "type": "string",
                        "enum": ["standard", "vegetarian", "vegan", "keto", "gluten-free"],
                    },
                    "cuisine_preference": {"type": "string"},
                    "budget": {"type": "string", "enum": ["low", "medium", "high"]},
                    "meals_per_day": {"type": "integer", "minimum": 2, "maximum": 6},
                    "allergies": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["calories_target", "goal", "diet_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_nutrition",
            "description": "Estimate meal macros and calories from a meal description",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_description": {"type": "string"},
                    "calorie_target": {"type": "integer"},
                },
                "required": ["meal_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_exercises",
            "description": "Search exercises by muscle group, difficulty, and equipment with safe alternatives",
            "parameters": {
                "type": "object",
                "properties": {
                    "muscle_group": {"type": "string"},
                    "equipment": {"type": "string"},
                    "difficulty": {"type": "string"},
                    "query": {"type": "string"},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recovery_protocol",
            "description": "Return recovery guidance and safe training modifications for injuries/soreness",
            "parameters": {
                "type": "object",
                "properties": {
                    "injury_type": {"type": "string"},
                    "severity": {"type": "string", "enum": ["mild", "moderate", "severe"]},
                },
                "required": ["injury_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_motivation_message",
            "description": "Generate personalized motivation based on consistency and communication style",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "consistency_score": {"type": "integer"},
                    "communication_style": {
                        "type": "string",
                        "enum": ["balanced", "casual", "formal", "high_motivation"],
                    },
                    "milestone": {"type": "string"},
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_smart_goal",
            "description": "Create a SMART goal and milestone breakdown",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_statement": {"type": "string"},
                    "timeframe_weeks": {"type": "integer"},
                    "current_value": {"type": "number"},
                    "target_value": {"type": "number"},
                    "metric": {"type": "string"},
                },
                "required": ["goal_statement", "timeframe_weeks", "current_value", "target_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_calories_burned",
            "description": "Estimate calories burned during exercise using MET values",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string", "description": "e.g. running, cycling, yoga"},
                    "duration_min": {"type": "integer"},
                    "weight_kg": {"type": "number"},
                    "intensity": {"type": "string", "enum": ["low", "moderate", "high"]},
                },
                "required": ["activity", "duration_min", "weight_kg", "intensity"],
            },
        },
    },
]

TOOL_MAP = {
    "calculate_bmi": calculate_bmi,
    "calculate_tdee": calculate_tdee,
    "generate_workout_plan": generate_workout_plan,
    "generate_meal_plan": generate_meal_plan,
    "analyze_nutrition": analyze_nutrition,
    "search_exercises": search_exercises,
    "get_recovery_protocol": get_recovery_protocol,
    "get_motivation_message": get_motivation_message,
    "create_smart_goal": create_smart_goal,
    "calculate_calories_burned": calculate_calories_burned,
}

SYSTEM_PROMPT = """You are APEX, an evidence-based health and fitness coaching agent.

Capabilities:
- Personalized workout planning with progression, substitutions, and recovery adjustments.
- Nutrition analysis and meal planning aligned with goals and restrictions.
- Exercise safety screening with injury-aware alternatives.
- SMART goal setting with milestone tracking.
- Motivational support based on consistency and communication preferences.

Behavior rules:
- Ask clarifying questions if required user context is missing.
- Use tools for plans, calculations, and structured recommendations.
- Explain recommendations with concise reasoning and practical steps.
- For injury/medical concerns include a safety disclaimer and escalate when needed.
- Keep responses actionable, encouraging, and specific.
"""

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class FitnessAgent:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at: https://console.groq.com"
            )
        self.client = Groq(api_key=api_key)
        self.history: list[dict[str, Any]] = []
        self.profile: dict[str, Any] = {}

    def update_profile(self, profile: dict):
        self.profile = {k: v for k, v in (profile or {}).items() if v is not None and v != ""}

    def load_state(self, profile: dict, history: list[dict]):
        self.profile = {k: v for k, v in (profile or {}).items() if v is not None and v != ""}
        self.history = []
        for m in history or []:
            role = m.get("role")
            if role in ("user", "assistant"):
                self.history.append({"role": role, "content": m.get("content", "")})

    def get_history(self):
        safe = []
        for m in self.history:
            if m.get("role") in ("user", "assistant"):
                safe.append({"role": m["role"], "content": m.get("content", "")})
        return safe

    def _profile_context(self) -> str:
        if not self.profile:
            return ""
        lines = ["[USER PROFILE]"] + [f"  {k}: {v}" for k, v in self.profile.items()]
        return "\n".join(lines) + "\n\n"

    def chat(self, user_message: str) -> dict:
        self.history.append({"role": "user", "content": user_message})
        tools_used: list[str] = []
        tool_results: list[dict[str, Any]] = []
        system = self._profile_context() + SYSTEM_PROMPT

        while True:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                max_tokens=1200,
                messages=[{"role": "system", "content": system}] + self.history,
                tools=TOOLS,
                tool_choice="auto",
            )

            msg = response.choices[0].message
            finish = response.choices[0].finish_reason
            tool_calls = msg.tool_calls or []

            if finish == "stop" or not tool_calls:
                reply = msg.content or ""
                self.history.append({"role": "assistant", "content": reply})
                return {
                    "reply": reply,
                    "tool_calls_used": tools_used,
                    "tool_results": tool_results,
                    "generated_at": _now_iso(),
                }

            self.history.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                tools_used.append(tc.function.name)
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = TOOL_MAP[tc.function.name](**args)
                except Exception as exc:
                    result = {"error": str(exc)}

                tool_results.append(
                    {
                        "name": tc.function.name,
                        "result": result,
                    }
                )

                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": json.dumps(result),
                    }
                )
