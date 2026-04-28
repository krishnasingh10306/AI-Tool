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
        SELECT id, user_message, ai_message
        FROM chat_history
        WHERE username = ?
        ORDER BY id ASC
    """, (username,)).fetchall()
    conn.close()
    return chats

# ==============================
# OTP FUNCTIONS
# ==============================

def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(receiver_email, otp):
    try:
        if not EMAIL_PASS:
            return False

        sender_email = "krishnasingh10306@gmail.com"

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = "OTP Verification"
        msg.attach(MIMEText(f"Your OTP is: {otp}", "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, EMAIL_PASS)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()

        return True

    except Exception as e:
        print("Email error:", e)
        return False

# ==============================
# AI TEXT
# ==============================

def generate_text(prompt):
    if client is None:
        return "Gemini API key not configured."

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        if hasattr(response, "text") and response.text:
            return response.text.strip()

        return "No response generated."

    except Exception as e:
        print("Gemini error:", e)
        return "AI service is temporarily unavailable."

# ==============================
# IMAGE LOGIC (HuggingFace)
# ==============================

def is_image_prompt(prompt):
    prompt = prompt.lower().strip()
    return prompt.startswith((
        "generate image",
        "create image",
        "draw",
        "image of",
        "photo of"
    ))


def clean_image_prompt(prompt):
    words_to_remove = [
        "generate image of",
        "create image of",
        "generate image",
        "create image",
        "image of",
        "photo of",
        "draw"
    ]

    cleaned = prompt.lower()
    for word in words_to_remove:
        cleaned = cleaned.replace(word, "")

    return cleaned.strip()


def generate_image(prompt):
    try:
        if not HF_TOKEN:
            return None, "HF_TOKEN not configured."

        final_prompt = clean_image_prompt(prompt)

        if not final_prompt:
            return None, "Invalid image prompt."

        api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

        headers = {
            "Authorization": f"Bearer {HF_TOKEN}"
        }

        response = requests.post(
            api_url,
            headers=headers,
            json={"inputs": final_prompt},
            timeout=180
        )

        if response.status_code != 200:
            print("HF error:", response.text)
            return None, f"HuggingFace error {response.status_code}"

        # Render safe path
        output_folder = os.path.join("static", "generated")
        os.makedirs(output_folder, exist_ok=True)

        filename = f"generated/img_{int(time.time())}.png"
        full_path = os.path.join("static", filename)

        with open(full_path, "wb") as f:
            f.write(response.content)

        return filename, None

    except Exception as e:
        print("Image error:", e)
        return None, "Image generation failed."

# ==============================
# RATE LIMIT
# ==============================

def check_rate_limit():
    last_request = session.get("last_request_time")
    if last_request and time.time() - last_request < 3:
        return False
    session["last_request_time"] = time.time()
    return True

# ==============================
# ROUTES
# ==============================

@app.route("/", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

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


@app.route("/main", methods=["GET", "POST"])
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
        image_file=None
    )


@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    if "user" not in session:
        return redirect(url_for("login_page"))

    if not check_rate_limit():
        flash("Please wait before sending another request.", "error")
        return redirect(url_for("main"))

    prompt = request.form.get("prompt", "").strip()

    if not prompt:
        return redirect(url_for("main"))

    chats = get_chat_history(session["user"])

    # IMAGE REQUEST
    if is_image_prompt(prompt):
        image_file, error = generate_image(prompt)

        if error:
            return render_template(
                "main.html",
                username=session["user"],
                chats=chats,
                current_user_message=prompt,
                current_ai_message=error,
                image_file=None
            )

        save_chat(session["user"], prompt, "Image generated.")

        return render_template(
            "main.html",
            username=session["user"],
            chats=get_chat_history(session["user"]),
            current_user_message=prompt,
            current_ai_message="Image generated successfully.",
            image_file=image_file
        )

    # TEXT REQUEST
    ai_reply = generate_text(prompt)
    save_chat(session["user"], prompt, ai_reply)

    return render_template(
        "main.html",
        username=session["user"],
        chats=get_chat_history(session["user"]),
        current_user_message=prompt,
        current_ai_message=ai_reply,
        image_file=None
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ==============================
# RENDER ENTRY POINT
# ==============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)