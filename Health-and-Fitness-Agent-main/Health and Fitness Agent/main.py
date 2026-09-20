"""
APEX Fitness Agent - FastAPI Backend
Run with: uvicorn main:app --reload --port 8000
"""

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import FitnessAgent

app = FastAPI(title="APEX Fitness Agent", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# ---- Runtime stores ---------------------------------------------------------

sessions: dict[str, FitnessAgent] = {}
# token -> {username, issued_at, last_seen}
tokens: dict[str, dict[str, str]] = {}

TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "24"))

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
STATE_FILE = DATA_DIR / "user_state.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return _now() - timedelta(days=9999)


def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")
    if not STATE_FILE.exists():
        STATE_FILE.write_text("{}", encoding="utf-8")


def _load_json(path: Path) -> dict:
    _ensure_data_files()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    _ensure_data_files()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _default_user_state() -> dict[str, Any]:
    return {
        "profile": {},
        "history": [],
        "progress_logs": [],
        "goals": [],
        "preferences": {
            "communication_style": "balanced",
            "tone": "friendly_professional",
        },
        "conversation_summary": "",
        "audit_log": [],
        "updated_at": _now_iso(),
    }


def _issue_token(username: str) -> str:
    token = secrets.token_urlsafe(32)
    now = _now_iso()
    tokens[token] = {"username": username, "issued_at": now, "last_seen": now}
    return token


def _token_expired(token_record: dict[str, str]) -> bool:
    last_seen = _parse_iso(token_record.get("last_seen", ""))
    return (_now() - last_seen).total_seconds() > TOKEN_TTL_HOURS * 3600


def _get_user_from_auth_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1].strip()
    token_record = tokens.get(token)
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid token")

    if _token_expired(token_record):
        tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expired")

    token_record["last_seen"] = _now_iso()
    return token_record["username"]


def _append_audit(username: str, event: str, details: Optional[dict[str, Any]] = None) -> None:
    state = _load_json(STATE_FILE)
    user_state = state.get(username, _default_user_state())
    user_state.setdefault("audit_log", []).append(
        {
            "at": _now_iso(),
            "event": event,
            "details": details or {},
        }
    )
    user_state["updated_at"] = _now_iso()
    state[username] = user_state
    _save_json(STATE_FILE, state)


def _state_for_user(username: str) -> dict[str, Any]:
    state = _load_json(STATE_FILE)
    user_state = state.get(username)
    if not user_state:
        user_state = _default_user_state()
        state[username] = user_state
        _save_json(STATE_FILE, state)
    # Backward compatibility for older state files.
    base = _default_user_state()
    base.update(user_state)
    return base


def _save_state_for_user(username: str, user_state: dict[str, Any]) -> None:
    state = _load_json(STATE_FILE)
    user_state["updated_at"] = _now_iso()
    state[username] = user_state
    _save_json(STATE_FILE, state)


def _get_or_create_agent(username: str) -> FitnessAgent:
    if username not in sessions:
        agent = FitnessAgent()
        user_state = _state_for_user(username)
        agent.load_state(user_state.get("profile", {}), user_state.get("history", []))
        sessions[username] = agent
    return sessions[username]


def _build_conversation_summary(history: list[dict[str, Any]]) -> str:
    if not history:
        return "No conversation history yet."
    recent = [h for h in history if str(h.get("content", "")).strip()][-8:]
    if not recent:
        return "No meaningful conversation content available."

    user_msgs = [m.get("content", "") for m in recent if m.get("role") == "user"]
    assistant_msgs = [m.get("content", "") for m in recent if m.get("role") == "assistant"]

    user_focus = "; ".join(x[:90] for x in user_msgs[-3:]) or "No recent user prompts"
    coach_actions = "; ".join(x[:90] for x in assistant_msgs[-2:]) or "No recent coach responses"
    return f"Recent user focus: {user_focus}. Recent coach guidance: {coach_actions}."


def _persist_user_state(username: str) -> None:
    if username not in sessions:
        return

    current = _state_for_user(username)
    current["profile"] = sessions[username].profile
    current["history"] = sessions[username].get_history()
    current["conversation_summary"] = _build_conversation_summary(current["history"])
    _save_state_for_user(username, current)


def _auto_log_calories_from_chat(username: str, response: dict[str, Any], user_message: str = "") -> int:
    tool_results = response.get("tool_results", []) or []
    if not isinstance(tool_results, list):
        return 0

    user_state = _state_for_user(username)
    progress_logs = user_state.setdefault("progress_logs", [])
    appended = 0
    logged_burned = False
    logged_intake = False

    for item in tool_results:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        result = item.get("result") or {}
        if not isinstance(result, dict):
            continue

        if name == "calculate_calories_burned":
            value = result.get("calories_burned")
            if isinstance(value, (int, float)) and float(value) > 0:
                progress_logs.append(
                    {
                        "at": _now_iso(),
                        "metric": "calories_burned",
                        "value": round(float(value)),
                        "notes": "Auto-logged from chat: calories burned estimate",
                    }
                )
                appended += 1
                logged_burned = True

        if name == "analyze_nutrition":
            totals = result.get("totals") or {}
            if isinstance(totals, dict):
                value = totals.get("calories")
                if isinstance(value, (int, float)) and float(value) > 0:
                    progress_logs.append(
                        {
                            "at": _now_iso(),
                            "metric": "calories_intake",
                            "value": round(float(value)),
                            "notes": "Auto-logged from chat: meal calorie estimate",
                        }
                    )
                    appended += 1
                    logged_intake = True

    reply = str(response.get("reply", "") or "")
    low = reply.lower()
    user_low = str(user_message or "").lower()

    def _has_food_context(text: str) -> bool:
        if not text:
            return False
        return bool(
            re.search(
                r"\b(meal|food|nutrition|serving|ate|eat|dish|breakfast|lunch|dinner|snack|biryani|rice|chicken)\b",
                text,
            )
        )

    # Fallback when model gives calorie values in plain text without tool calls.
    if not logged_burned:
        burn_match = re.search(r"burn(?:ed|t)?[^\d]{0,24}(\d+(?:\.\d+)?)\s*cal", low)
        if burn_match:
            burned_value = float(burn_match.group(1))
            if burned_value > 0:
                progress_logs.append(
                    {
                        "at": _now_iso(),
                        "metric": "calories_burned",
                        "value": round(burned_value),
                        "notes": "Auto-logged from chat reply text",
                    }
                )
                appended += 1

    if not logged_intake:
        intake_context = _has_food_context(low) or _has_food_context(user_low)
        likely_burn_reply = bool(re.search(r"\bburn(?:ed|t)?\b", low))
        intake_match = re.search(r"(\d+(?:\.\d+)?)\s*calories", low)
        if intake_context and intake_match and not likely_burn_reply:
            intake_value = float(intake_match.group(1))
            if intake_value > 0:
                progress_logs.append(
                    {
                        "at": _now_iso(),
                        "metric": "calories_intake",
                        "value": round(intake_value),
                        "notes": "Auto-logged from chat reply text",
                    }
                )
                appended += 1

    if appended:
        user_state["progress_analytics"] = _compute_progress_analytics(progress_logs)
        _save_state_for_user(username, user_state)

    return appended


def _compute_progress_analytics(progress_logs: list[dict[str, Any]]) -> dict[str, Any]:
    if not progress_logs:
        return {
            "entries": 0,
            "consistency_score": 0,
            "weight_trend": "insufficient_data",
            "strength_trend": "insufficient_data",
            "plateau_detected": False,
            "calories_logged_total": 0,
            "calories_logged_average": 0,
            "calories_entries": 0,
            "calories_burned_total": 0,
            "daily_calories": [],
            "insights": ["Log at least 3 entries to unlock trend analysis."],
        }

    entries = len(progress_logs)
    workout_done = [x for x in progress_logs if x.get("metric") == "workout_completed" and x.get("value")]
    weight_points = [float(x.get("value")) for x in progress_logs if x.get("metric") == "weight_kg"]
    strength_points = [float(x.get("value")) for x in progress_logs if x.get("metric") == "strength_pr"]
    calories_points = [
        float(x.get("value"))
        for x in progress_logs
        if x.get("metric") in {"calories", "calories_intake"} and str(x.get("value", "")).strip() != ""
    ]
    calories_burned_points = [
        float(x.get("value"))
        for x in progress_logs
        if x.get("metric") == "calories_burned" and str(x.get("value", "")).strip() != ""
    ]

    consistency_score = min(100, round((len(workout_done) / max(1, entries)) * 100))

    weight_trend = "stable"
    if len(weight_points) >= 2:
        delta = weight_points[-1] - weight_points[0]
        if delta <= -0.4:
            weight_trend = "decreasing"
        elif delta >= 0.4:
            weight_trend = "increasing"

    strength_trend = "stable"
    if len(strength_points) >= 2:
        delta = strength_points[-1] - strength_points[0]
        if delta >= 2:
            strength_trend = "improving"
        elif delta <= -2:
            strength_trend = "declining"

    plateau_detected = False
    if len(weight_points) >= 4:
        window = weight_points[-4:]
        plateau_detected = max(window) - min(window) <= 0.3

    calories_logged_total = round(sum(calories_points)) if calories_points else 0
    calories_logged_average = round(sum(calories_points) / len(calories_points)) if calories_points else 0

    daily_map: dict[str, dict[str, Any]] = {}
    for log in progress_logs:
        metric = str(log.get("metric", "")).strip().lower()
        if metric not in {"calories", "calories_intake", "calories_burned"}:
            continue

        try:
            value = float(log.get("value"))
        except Exception:
            continue
        if value <= 0:
            continue

        at = str(log.get("at", "")).strip()
        try:
            day_key = _parse_iso(at).date().isoformat()
        except Exception:
            day_key = at.split("T", 1)[0] if at else _now().date().isoformat()

        if day_key not in daily_map:
            daily_map[day_key] = {
                "date": day_key,
                "intake": 0,
                "burned": 0,
                "net": 0,
            }

        if metric == "calories_burned":
            daily_map[day_key]["burned"] += value
        else:
            daily_map[day_key]["intake"] += value

    daily_calories = []
    for day_key in sorted(daily_map.keys())[-14:]:
        row = daily_map[day_key]
        intake = round(row["intake"])
        burned = round(row["burned"])
        daily_calories.append(
            {
                "date": row["date"],
                "intake": intake,
                "burned": burned,
                "net": intake - burned,
            }
        )

    insights = []
    if consistency_score >= 80:
        insights.append("Excellent adherence. Keep progressive overload and recovery balanced.")
    elif consistency_score >= 55:
        insights.append("Good consistency. Add one additional planned session this week.")
    else:
        insights.append("Consistency is the biggest lever right now. Start with 3 fixed sessions/week.")

    if plateau_detected:
        insights.append("Plateau detected. Consider a calorie adjustment or training intensity progression.")

    return {
        "entries": entries,
        "consistency_score": consistency_score,
        "weight_trend": weight_trend,
        "strength_trend": strength_trend,
        "plateau_detected": plateau_detected,
        "calories_logged_total": calories_logged_total,
        "calories_logged_average": calories_logged_average,
        "calories_entries": len(calories_points),
        "calories_burned_total": round(sum(calories_burned_points)) if calories_burned_points else 0,
        "daily_calories": daily_calories,
        "insights": insights,
    }


# ---- Schemas ----------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    user_profile: Optional[dict] = None


class ProfileRequest(BaseModel):
    profile: dict


class AuthRequest(BaseModel):
    username: str
    password: str


class ProgressLogRequest(BaseModel):
    metric: str = Field(description="weight_kg, measurements_cm, strength_pr, workout_completed, calories")
    value: Any
    notes: Optional[str] = ""
    date: Optional[str] = ""


class GoalRequest(BaseModel):
    title: str
    metric: str
    current_value: float
    target_value: float
    due_date: Optional[str] = ""


class PreferenceRequest(BaseModel):
    communication_style: Optional[str] = None
    tone: Optional[str] = None


class PasswordResetRequest(BaseModel):
    username: str
    new_password: str


# ---- Frontend routes --------------------------------------------------------

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.get("/login")
async def login_page():
    return FileResponse("frontend/login.html")


@app.get("/app")
async def app_page():
    return FileResponse("frontend/app.html")


# ---- Auth routes ------------------------------------------------------------

@app.post("/api/auth/signup")
async def signup(req: AuthRequest):
    username = req.username.strip().lower()
    password = req.password.strip()

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    users = _load_json(USERS_FILE)
    if username in users:
        raise HTTPException(status_code=409, detail="Username already exists")

    salt = secrets.token_hex(16)
    users[username] = {
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at": _now_iso(),
    }
    _save_json(USERS_FILE, users)

    # Initialize persisted state.
    _save_state_for_user(username, _default_user_state())
    token = _issue_token(username)
    _get_or_create_agent(username)
    _append_audit(username, "signup")

    return {"token": token, "username": username, "token_ttl_hours": TOKEN_TTL_HOURS}


@app.post("/api/auth/login")
async def login(req: AuthRequest):
    username = req.username.strip().lower()
    password = req.password.strip()

    users = _load_json(USERS_FILE)
    user = users.get(username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    expected = _hash_password(password, user.get("salt", ""))
    if expected != user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = _issue_token(username)
    _get_or_create_agent(username)
    _append_audit(username, "login")
    return {"token": token, "username": username, "token_ttl_hours": TOKEN_TTL_HOURS}


@app.post("/api/auth/reset-password")
async def reset_password(req: PasswordResetRequest):
    username = req.username.strip().lower()
    new_password = req.new_password.strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    users = _load_json(USERS_FILE)
    user = users.get(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    salt = secrets.token_hex(16)
    users[username]["salt"] = salt
    users[username]["password_hash"] = _hash_password(new_password, salt)
    users[username]["password_updated_at"] = _now_iso()
    _save_json(USERS_FILE, users)

    # Revoke existing tokens for this user.
    for tkn, rec in list(tokens.items()):
        if rec.get("username") == username:
            tokens.pop(tkn, None)

    _append_audit(username, "password_reset")
    return {"status": "ok"}


@app.get("/api/auth/me")
async def me(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    return {"username": username}


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        token_record = tokens.get(token)
        if token_record:
            _append_audit(token_record["username"], "logout")
        tokens.pop(token, None)
    return {"status": "ok"}


# ---- Core agent routes ------------------------------------------------------

@app.post("/api/chat")
async def chat(req: ChatRequest, authorization: Optional[str] = Header(default=None)):
    try:
        username = _get_user_from_auth_header(authorization)
        agent = _get_or_create_agent(username)

        if req.user_profile:
            agent.update_profile(req.user_profile)

        response = agent.chat(req.message)
        auto_logs = _auto_log_calories_from_chat(username, response, req.message)
        _persist_user_state(username)
        _append_audit(
            username,
            "chat",
            {
                "tool_calls": response.get("tool_calls_used", []),
                "auto_calorie_logs": auto_logs,
            },
        )

        return {
            "reply": response.get("reply", ""),
            "tool_calls_used": response.get("tool_calls_used", []),
            "generated_at": response.get("generated_at"),
            "session_id": username,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/profile")
async def set_profile(req: ProfileRequest, authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    agent = _get_or_create_agent(username)
    agent.update_profile(req.profile)
    _persist_user_state(username)
    _append_audit(username, "profile_update", {"keys": list(req.profile.keys())})
    return {"status": "ok", "profile": agent.profile}


@app.post("/api/preferences")
async def set_preferences(req: PreferenceRequest, authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)
    prefs = user_state.get("preferences", {})
    if req.communication_style:
        prefs["communication_style"] = req.communication_style
    if req.tone:
        prefs["tone"] = req.tone
    user_state["preferences"] = prefs
    _save_state_for_user(username, user_state)
    _append_audit(username, "preferences_update", prefs)
    return {"status": "ok", "preferences": prefs}


@app.get("/api/session/history")
async def get_history(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    agent = _get_or_create_agent(username)
    user_state = _state_for_user(username)
    analytics = _compute_progress_analytics(user_state.get("progress_logs", []))
    return {
        "history": agent.get_history(),
        "profile": agent.profile,
        "progress_analytics": analytics,
        "goals": user_state.get("goals", []),
        "summary": user_state.get("conversation_summary", ""),
    }


@app.get("/api/session/search")
async def search_history(
    authorization: Optional[str] = Header(default=None),
    q: str = Query(min_length=2, description="Search phrase"),
):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)
    history = user_state.get("history", [])
    query = q.lower().strip()

    matches = []
    for item in history:
        content = str(item.get("content", ""))
        if query in content.lower():
            matches.append(
                {
                    "role": item.get("role", "unknown"),
                    "content": content,
                    "preview": content[:140],
                }
            )

    return {"query": q, "count": len(matches), "matches": matches[:40]}


@app.get("/api/session/summary")
async def get_session_summary(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)
    return {"summary": user_state.get("conversation_summary", "")}


@app.delete("/api/session")
async def clear_session(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    if username in sessions:
        del sessions[username]

    user_state = _state_for_user(username)
    user_state["history"] = []
    user_state["conversation_summary"] = ""
    _save_state_for_user(username, user_state)
    _append_audit(username, "session_cleared")
    return {"status": "cleared"}


# ---- Progress and goals -----------------------------------------------------

@app.post("/api/progress/log")
async def log_progress(req: ProgressLogRequest, authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)

    entry = {
        "at": req.date or _now_iso(),
        "metric": req.metric,
        "value": req.value,
        "notes": req.notes or "",
    }
    user_state.setdefault("progress_logs", []).append(entry)

    analytics = _compute_progress_analytics(user_state.get("progress_logs", []))
    user_state["progress_analytics"] = analytics
    _save_state_for_user(username, user_state)

    _append_audit(username, "progress_log", {"metric": req.metric})
    return {"status": "ok", "entry": entry, "analytics": analytics}


@app.get("/api/progress/history")
async def progress_history(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)
    return {"progress_logs": user_state.get("progress_logs", [])}


@app.get("/api/progress/analytics")
async def progress_analytics(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)
    analytics = _compute_progress_analytics(user_state.get("progress_logs", []))
    return {"analytics": analytics}


@app.post("/api/goals")
async def create_goal(req: GoalRequest, authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)

    goal = {
        "id": secrets.token_hex(8),
        "title": req.title,
        "metric": req.metric,
        "current_value": req.current_value,
        "target_value": req.target_value,
        "progress_percent": 0,
        "due_date": req.due_date,
        "status": "active",
        "created_at": _now_iso(),
    }

    if req.target_value != req.current_value:
        span = req.target_value - req.current_value
        done = 0.0
        goal["progress_percent"] = max(0, min(100, round((done / span) * 100 if span else 0)))

    user_state.setdefault("goals", []).append(goal)
    _save_state_for_user(username, user_state)
    _append_audit(username, "goal_created", {"goal_id": goal["id"]})
    return {"status": "ok", "goal": goal}


@app.get("/api/goals")
async def list_goals(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)
    return {"goals": user_state.get("goals", [])}


# ---- Privacy, export, and account management -------------------------------

@app.get("/api/user/export")
async def export_user_data(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)

    payload = {
        "username": username,
        "exported_at": _now_iso(),
        "state": user_state,
    }
    return payload


@app.get("/api/export/plan")
async def export_plan_document(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)
    user_state = _state_for_user(username)

    history = user_state.get("history", [])
    recent_assistant = [m.get("content", "") for m in history if m.get("role") == "assistant"][-4:]
    body = "\n\n".join(recent_assistant) if recent_assistant else "No plan found in recent history."

    doc = (
        "APEX PLAN EXPORT\n"
        f"User: {username}\n"
        f"Generated: {_now_iso()}\n\n"
        "Recent coach plans/recommendations:\n"
        f"{body}\n"
    )

    return PlainTextResponse(content=doc, media_type="text/plain")


@app.delete("/api/user/account")
async def delete_account(authorization: Optional[str] = Header(default=None)):
    username = _get_user_from_auth_header(authorization)

    users = _load_json(USERS_FILE)
    users.pop(username, None)
    _save_json(USERS_FILE, users)

    state = _load_json(STATE_FILE)
    state.pop(username, None)
    _save_json(STATE_FILE, state)

    sessions.pop(username, None)
    for tkn, rec in list(tokens.items()):
        if rec.get("username") == username:
            tokens.pop(tkn, None)

    return {"status": "deleted", "username": username}


# ---- Health ----------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "sessions_active": len(sessions),
        "tokens_active": len(tokens),
        "token_ttl_hours": TOKEN_TTL_HOURS,
    }
