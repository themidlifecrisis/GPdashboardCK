"""Authentication and role-based access control."""

import base64
import os

import bcrypt
import streamlit as st

from config import ROLE_ACCOUNTANT, ROLE_ADMIN, ROLE_DIRECTOR, ROLE_MANAGER

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")


def _logo_b64():
    """Read the logo file and return a base64-encoded string."""
    with open(LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def login_form(users_data) -> bool:
    """Render login form and authenticate user.

    users_data: list of dicts with keys: username, password_hash, role, branch, name
    Returns True if user is authenticated.
    """
    if st.session_state.get("authenticated"):
        return True

    logo_data = _logo_b64()
    st.markdown(
        f"""
        <div style="text-align: center; padding: 2rem 0 0.5rem 0;">
            <img src="data:image/png;base64,{logo_data}" width="150" style="border-radius: 50%;" />
            <h1 style="color: #1E88E5; margin: 0.8rem 0 0.2rem 0;">GP Dashboard</h1>
            <p style="color: #666; font-size: 1.1rem;">Gross Profit Calculations &amp; Analysis</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                user = next(
                    (u for u in users_data if u.get("username", "").lower() == username.lower()),
                    None,
                )
                if user and verify_password(password, user["password_hash"]):
                    st.session_state["authenticated"] = True
                    st.session_state["user_email"] = user["username"]
                    st.session_state["user_role"] = user["role"]
                    st.session_state["user_branch"] = user.get("branch", "All")
                    st.session_state["user_name"] = user.get("name", user["username"])
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    return False


def logout():
    """Clear session and log out."""
    for key in ["authenticated", "user_email", "user_role", "user_branch", "user_name"]:
        st.session_state.pop(key, None)
    st.rerun()


def require_auth(func):
    """Decorator: only run the function if user is authenticated."""
    def wrapper(*args, **kwargs):
        if not st.session_state.get("authenticated"):
            st.warning("Please sign in to continue.")
            st.stop()
        return func(*args, **kwargs)
    return wrapper


def is_director() -> bool:
    """Check if current user has director-level view access (director, admin, or accountant)."""
    return st.session_state.get("user_role") in (ROLE_DIRECTOR, ROLE_ADMIN, ROLE_ACCOUNTANT)


def is_manager() -> bool:
    """Check if current user is a branch manager."""
    return st.session_state.get("user_role") == ROLE_MANAGER


def can_edit_budgets() -> bool:
    """Check if user can edit budgets and settings (director, accountant)."""
    return st.session_state.get("user_role") in (ROLE_DIRECTOR, ROLE_ACCOUNTANT)


def can_edit_actuals() -> bool:
    """Check if user can edit actuals (manager for own branch, accountant for all)."""
    return st.session_state.get("user_role") in (ROLE_MANAGER, ROLE_ACCOUNTANT)


def get_user_branch() -> str:
    """Get the branch assigned to the current user."""
    return st.session_state.get("user_branch", "")


def get_allowed_branches(all_branches):
    """Return branches the current user is allowed to view."""
    if is_director():
        return all_branches
    return [get_user_branch()]
