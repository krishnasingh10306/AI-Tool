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

# ==============================
# SAFE DB INIT
# ==============================
try:
    create_table()
except Exception as e:
    print("DB INIT ERROR:", e)

# ==============================
# ENV VARIABLES
# ==============================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_USER = os.getenv("EMAIL_USER")
HF_TOKEN = os.getenv("HF_TOKEN")

client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print("Gemini init error:", e)


# ==============================
# DATABASE HELPERS
# ==============================
def save_chat(username, user_message, ai_message):
    try:
        conn = db()
        conn.execute("""
            INSERT INTO chat_history (username, user_message, ai_message)
            VALUES (?, ?, ?)
        """, (username, user_message, ai_message))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Save chat error:", e)


def get_chat_history(username):
    try:
        conn = db()
        chats = conn.execute("""
            SELECT * FROM chat_history
            WHERE username = ?
            ORDER BY id ASC
        """, (username,)).fetchall()
        conn.close()
        return chats
    except Exception as e:
        print("Get chat error:", e)
        return []


# ==============================
# OTP EMAIL
# ==============================
def send_otp_email(receiver_email, otp):
    try:
        if not EMAIL_USER or not EMAIL_PASS:
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

    except Exception as e:
        print("Email error:", e)
        return False


def generate_otp():
    return str(random.randint(100000, 999999))


# ==============================
# GEMINI AI
# ==============================
def generate_text(prompt):
    try:
        if not client:
            return "AI not configured."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text.strip() if response.text else "No response"

    except Exception as e:
        print("Gemini error:", e)
        return "AI service error"


# ==============================
# IMAGE GENERATION
# ==============================
def generate_image(prompt):
    try:
        if not HF_TOKEN:
            return None, "HF_TOKEN missing"

        api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}

        response = requests.post(
            api_url,
            headers=headers,
            json={"inputs": prompt},
            timeout=120
        )

        if response.status_code != 200:
            return None, "Image API failed"

        os.makedirs("static/generated", exist_ok=True)

        filename = f"generated/img_{int(time.time())}.png"
        path = os.path.join("static", filename)

        with open(path, "wb") as f:
            f.write(response.content)

        return filename, None

    except Exception as e:
        print("Image error:", e)
        return None, "Image generation failed"


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

        flash("Invalid login", "error")

    return render_template("login.html")


# ==============================
# MAIN PAGE (FIXED)
# ==============================
@app.route("/main")
def main():
    user = session.get("user")

    if not user:
        return redirect(url_for("login_page"))

    chats = get_chat_history(user) or []

    return render_template(
        "main.html",
        username=user,
        chats=chats,
        current_user_message=None,
        current_ai_message=None,
        image_file=None,
        quick_prompt="",
        search_keyword=""
    )


# ==============================
# ASK AI (FIXED)
# ==============================
@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    user = session.get("user")
    if not user:
        return redirect(url_for("login_page"))

    prompt = request.form.get("prompt")

    if not prompt or prompt.strip() == "":
        return redirect(url_for("main"))

    if "generate image" in prompt.lower() or "create image" in prompt.lower():
        image_file, error = generate_image(prompt)
        reply = error if error else "Image generated"
    else:
        reply = generate_text(prompt)
        image_file = None

    save_chat(user, prompt, reply)

    return render_template(
        "main.html",
        username=user,
        chats=get_chat_history(user),
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
# RUN
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)