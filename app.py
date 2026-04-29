# ==============================
# IMPORTS
# ==============================
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import db, create_table
from validation import password_validation, valid_email

import random
import smtplib
import os
import time
import requests

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google import genai
from werkzeug.security import generate_password_hash, check_password_hash


# ==============================
# APP SETUP
# ==============================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_fallback_key")

create_table()

# ==============================
# ENV VARIABLES
# ==============================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_USER = os.getenv("EMAIL_USER")
HF_TOKEN = os.getenv("HF_TOKEN")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)


# ==============================
# DATABASE HELPERS
# ==============================
def save_chat(username, user_message, ai_message):
    conn = db()
    conn.execute("""
        INSERT INTO chat_history (username, user_message, ai_message)
        VALUES (?, ?, ?)
    """, (username, user_message, ai_message))
    conn.commit()
    conn.close()


def get_chat_history(username):
    conn = db()
    chats = conn.execute("""
        SELECT * FROM chat_history
        WHERE username = ?
        ORDER BY id ASC
    """, (username,)).fetchall()
    conn.close()
    return chats


# ==============================
# OTP
# ==============================
def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(receiver_email, otp):
    try:
        if not EMAIL_PASS or not EMAIL_USER:
            return False

        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = receiver_email
        msg["Subject"] = "OTP Verification"
        msg.attach(MIMEText(f"Your OTP is: {otp}", "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, receiver_email, msg.as_string())
        server.quit()
        return True

    except Exception:
        return False


# ==============================
# GEMINI TEXT
# ==============================
def generate_text(prompt):
    if client is None:
        return "Gemini API not configured."

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip() if response.text else "No response generated."
    except Exception:
        return "AI service temporarily unavailable."


# ==============================
# IMAGE GENERATION
# ==============================
def is_image_prompt(prompt):
    prompt = prompt.lower()
    return any(word in prompt for word in [
        "generate image", "create image", "draw",
        "image of", "photo of"
    ])


def clean_image_prompt(prompt):
    words = [
        "generate image of", "create image of",
        "generate image", "create image",
        "image of", "photo of", "draw"
    ]
    cleaned = prompt.lower()
    for w in words:
        cleaned = cleaned.replace(w, "")
    return cleaned.strip()


def generate_image(prompt):
    try:
        if not HF_TOKEN:
            return None, "HF_TOKEN not configured."

        final_prompt = clean_image_prompt(prompt)

        api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

        headers = {
            "Authorization": f"Bearer {HF_TOKEN}"
        }

        response = requests.post(
            api_url,
            headers=headers,
            json={"inputs": final_prompt},
            timeout=120
        )

        if response.status_code != 200:
            return None, "Image generation failed."

        os.makedirs("static/generated", exist_ok=True)

        filename = f"generated/img_{int(time.time())}.png"
        full_path = os.path.join("static", filename)

        with open(full_path, "wb") as f:
            f.write(response.content)

        return filename, None

    except Exception:
        return None, "Image generation failed."


# ==============================
# LOGIN
# ==============================
@app.route("/", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            return redirect(url_for("main"))

        flash("Invalid email or password", "error")

    return render_template("login.html")


# ==============================
# SIGNUP
# ==============================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fullname = request.form.get("fullname")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not valid_email(email):
            flash("Invalid email", "error")
            return render_template("signup.html")

        if not password_validation(password):
            flash("Weak password", "error")
            return render_template("signup.html")

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("signup.html")

        conn = db()
        existing = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:
            conn.close()
            flash("Email already exists", "error")
            return render_template("signup.html")

        hashed = generate_password_hash(password)

        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (fullname, email, hashed)
        )
        conn.commit()
        conn.close()

        flash("Signup successful. Please login.", "success")
        return redirect(url_for("login_page"))

    return render_template("signup.html")


# ==============================
# FORGOT PASSWORD
# ==============================
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if not user:
            flash("Email not found", "error")
            return render_template("forgot_password.html")

        otp = generate_otp()
        session["reset_email"] = email
        session["reset_otp"] = otp

        if send_otp_email(email, otp):
            flash("OTP sent to your email", "success")
            return redirect(url_for("reset_otp"))

        flash("Failed to send OTP", "error")

    return render_template("forgot_password.html")


# ==============================
# RESET OTP
# ==============================
@app.route("/reset_otp", methods=["GET", "POST"])
def reset_otp():
    if request.method == "POST":
        user_otp = request.form.get("otp")

        if user_otp == session.get("reset_otp"):
            flash("OTP verified. Set new password.", "success")
            return redirect(url_for("reset_password"))

        flash("Invalid OTP", "error")

    return render_template("reset_otp.html")


# ==============================
# RESET PASSWORD
# ==============================
@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        new_password = request.form.get("new_password")

        if not password_validation(new_password):
            flash("Weak password", "error")
            return render_template("reset_password.html")

        hashed = generate_password_hash(new_password)

        conn = db()
        conn.execute(
            "UPDATE users SET password = ? WHERE email = ?",
            (hashed, session.get("reset_email"))
        )
        conn.commit()
        conn.close()

        session.pop("reset_email", None)
        session.pop("reset_otp", None)

        flash("Password updated successfully", "success")
        return redirect(url_for("login_page"))

    return render_template("reset_password.html")


# ==============================
# MAIN
# ==============================
@app.route("/main")
def main():
    if "user" not in session:
        return redirect(url_for("login_page"))

    chats = get_chat_history(session["user"])

    return render_template(
        "main.html",
        username=session["user"],
        chats=chats,
        current_user_message=None,
        current_ai_message=None,
        image_file=None,
        quick_prompt="",
        search_keyword=""
    )


# ==============================
# ASK AI
# ==============================
@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    if "user" not in session:
        return redirect(url_for("login_page"))

    prompt = request.form.get("prompt")

    if is_image_prompt(prompt):
        image_file, error = generate_image(prompt)
        reply = error if error else "Image generated successfully."
    else:
        reply = generate_text(prompt)
        image_file = None

    save_chat(session["user"], prompt, reply)

    return render_template(
        "main.html",
        username=session["user"],
        chats=get_chat_history(session["user"]),
        current_user_message=prompt,
        current_ai_message=reply,
        image_file=image_file,
        quick_prompt="",
        search_keyword=""
    )


# ==============================
# LOGOUT
# ==============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ==============================
# ENTRY POINT
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)