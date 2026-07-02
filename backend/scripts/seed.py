"""Seed sample teams, users, and memberships for local development.

Idempotent: re-running will not duplicate rows. Run with:
    uv run python -m backend.scripts.seed
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.db.session import SessionLocal
from backend.app.models import Membership, Team, User

DEFAULT_PASSWORD = "password123"

TEAMS = ["Engineering", "Marketing"]

# email -> (display_name, [team names])
USERS = {
    "alice@vng.com.vn": ("Alice", ["Engineering"]),
    "bob@vng.com.vn": ("Bob", ["Marketing"]),
    "carol@vng.com.vn": ("Carol", ["Engineering", "Marketing"]),
}


def get_or_create_team(db: Session, name: str) -> Team:
    team = db.scalar(select(Team).where(Team.name == name))
    if team is None:
        team = Team(name=name)
        db.add(team)
        db.flush()
    return team


def get_or_create_user(db: Session, email: str, display_name: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            hashed_password=hash_password(DEFAULT_PASSWORD),
        )
        db.add(user)
        db.flush()
    return user


def ensure_membership(db: Session, user: User, team: Team) -> None:
    existing = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.team_id == team.id
        )
    )
    if existing is None:
        db.add(Membership(user_id=user.id, team_id=team.id))


def main() -> None:
    db = SessionLocal()
    try:
        teams = {name: get_or_create_team(db, name) for name in TEAMS}
        for email, (display_name, team_names) in USERS.items():
            user = get_or_create_user(db, email, display_name)
            for tn in team_names:
                ensure_membership(db, user, teams[tn])
        db.commit()
        print("Seed complete.")
        print(f"  Teams:  {', '.join(TEAMS)}")
        print(f"  Users:  {', '.join(USERS)}  (password: {DEFAULT_PASSWORD})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
